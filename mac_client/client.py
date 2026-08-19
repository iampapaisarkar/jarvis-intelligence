"""Connect to the Windows brain over LAN WebSocket and run Mac tools."""

from __future__ import annotations

import argparse
import asyncio
import json
import socket
import sys
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from server import __version__
from server.config import get_settings
from server.mac.protocol import ALLOWED_FROM_BRAIN, ErrorMessage, ToolRequestMessage
from server.utils.logger import get_logger, setup_logging

from mac_client.runner import MacToolRunner

logger = get_logger("jarvis.mac.client")


def _with_token_query(url: str, token: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("token", token)
    return urlunparse(parsed._replace(query=urlencode(query)))


def _connect(url: str, token: str):
    import websockets

    headers = {"X-Jarvis-Token": token}
    try:
        return websockets.connect(url, additional_headers=headers)
    except TypeError:
        return websockets.connect(url, extra_headers=headers)


async def run_client(
    *,
    url: str,
    token: str,
    runner: MacToolRunner,
    once: bool = False,
) -> None:
    target = _with_token_query(url, token)
    hostname = socket.gethostname()[:128]
    delay = 2.0
    while True:
        try:
            async with _connect(target, token) as ws:
                delay = 2.0
                await ws.send(
                    json.dumps(
                        {
                            "type": "hello",
                            "role": "mac-client",
                            "hostname": hostname,
                            "version": __version__,
                        }
                    )
                )
                raw = await ws.recv()
                hello = json.loads(raw)
                if hello.get("type") != "hello_ok":
                    logger.error("handshake failed: %s", hello)
                    if once:
                        return
                    await asyncio.sleep(delay)
                    continue
                logger.info("connected to brain session=%s", hello.get("session_id"))
                async for message in ws:
                    await _handle_brain_message(ws, message, runner)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("mac client disconnected")
            if once:
                return
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)


async def _handle_brain_message(ws: Any, message: Any, runner: MacToolRunner) -> None:
    if isinstance(message, bytes):
        message = message.decode("utf-8")
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        await ws.send(ErrorMessage(error="invalid_json", detail="Message must be JSON.").model_dump_json())
        return
    if not isinstance(data, dict):
        await ws.send(ErrorMessage(error="invalid_json", detail="Message must be a JSON object.").model_dump_json())
        return
    kind = str(data.get("type") or "")
    if kind not in ALLOWED_FROM_BRAIN:
        await ws.send(
            ErrorMessage(error="unknown_message", detail=f"Unsupported type: {kind or 'missing'}").model_dump_json()
        )
        return
    if kind == "ping":
        await ws.send(json.dumps({"type": "pong"}))
        return
    if kind in {"pong", "hello_ok", "error"}:
        return
    if kind == "tool_request":
        request = ToolRequestMessage.model_validate(data)
        result = runner.handle_request(
            request.tool,
            request.arguments,
            session_id=request.session_id,
        )
        await ws.send(
            json.dumps(
                {
                    "type": "tool_result",
                    "request_id": request.request_id,
                    "ok": result.ok,
                    "executed": result.executed,
                    "spoken": result.spoken,
                    "reason": result.reason,
                    "data": result.data,
                }
            )
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jarvis Mac body client")
    parser.add_argument(
        "--url",
        default=None,
        help="Brain WebSocket URL (default: ws://127.0.0.1:8765/v1/mac)",
    )
    parser.add_argument("--token", default=None, help="Shared JARVIS_AUTH_TOKEN")
    parser.add_argument("--once", action="store_true", help="Exit after the first disconnect")
    parser.add_argument("--wake", action="store_true", help="Listen for 'Jarvis' on this Mac's microphone")
    parser.add_argument(
        "--http-url",
        default=None,
        help="Brain HTTP base (default: derived from --url, e.g. http://127.0.0.1:8765)",
    )
    parser.add_argument("--wake-window", type=float, default=2.5, help="Seconds per wake clip")
    parser.add_argument("--command-seconds", type=float, default=5.0, help="Seconds to record after a bare 'Jarvis'")
    parser.add_argument(
        "--no-ptt-fallback",
        action="store_true",
        help="Ignore clips that do not start with the wake word",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    setup_logging(settings)
    url = args.url or "ws://127.0.0.1:8765/v1/mac"
    token = args.token or settings.jarvis_auth_token
    if not token:
        print("Missing auth token. Pass --token or set JARVIS_AUTH_TOKEN.", file=sys.stderr)
        raise SystemExit(2)
    runner = MacToolRunner(settings)

    async def _run() -> None:
        tasks = [asyncio.create_task(run_client(url=url, token=token, runner=runner, once=args.once))]
        if args.wake:
            from mac_client.wake import brain_http_base, run_wake_loop

            http_base = (args.http_url or brain_http_base(url)).rstrip("/")
            tasks.append(
                asyncio.create_task(
                    run_wake_loop(
                        http_base=http_base,
                        token=token,
                        window_seconds=args.wake_window,
                        command_seconds=args.command_seconds,
                        ptt_fallback=not args.no_ptt_fallback,
                        once=args.once,
                    )
                )
            )
        await asyncio.gather(*tasks)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("mac client stopped")
