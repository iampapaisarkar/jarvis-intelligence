"""Optional Mac-side wake loop: record a clip, ask the brain, then send the command."""

from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from server.utils.audio import record_microphone
from server.utils.logger import get_logger

logger = get_logger("jarvis.mac.wake")


def brain_http_base(ws_url: str) -> str:
    parsed = urlparse(ws_url)
    scheme = "https" if parsed.scheme == "wss" else "http"
    return urlunparse((scheme, parsed.netloc, "", "", "", "")).rstrip("/")


async def run_wake_loop(
    *,
    http_base: str,
    token: str,
    window_seconds: float = 2.5,
    command_seconds: float = 5.0,
    ptt_fallback: bool = True,
    once: bool = False,
) -> None:
    import httpx

    headers = {"X-Jarvis-Token": token}
    timeout = httpx.Timeout(60.0)
    logger.info("wake loop http=%s window=%s", http_base, window_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            tmp = Path(tempfile.mkdtemp(prefix="jarvis-wake-")) / "clip.wav"
            try:
                record_microphone(tmp, duration_seconds=window_seconds)
                with tmp.open("rb") as handle:
                    response = await client.post(
                        f"{http_base}/v1/wake/audio",
                        headers=headers,
                        files={"audio": ("clip.wav", handle, "audio/wav")},
                        data={"fallback": "true" if ptt_fallback else "false"},
                    )
                response.raise_for_status()
                body = response.json()
                command = (body.get("command") or "").strip()
                if body.get("heard") and not command:
                    command = await _record_command(client, headers, http_base, command_seconds)
                if command:
                    logger.info("wake command chars=%s heard=%s", len(command), body.get("heard"))
                    await client.post(
                        f"{http_base}/v1/intent",
                        headers={**headers, "Content-Type": "application/json"},
                        json={"text": command, "target": "mac"},
                    )
            except Exception:
                logger.exception("wake loop cycle failed")
            finally:
                try:
                    tmp.unlink(missing_ok=True)
                    tmp.parent.rmdir()
                except OSError:
                    pass
            if once:
                return


async def _record_command(client, headers: dict[str, str], http_base: str, seconds: float) -> str:
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-cmd-")) / "cmd.wav"
    try:
        record_microphone(tmp, duration_seconds=seconds)
        with tmp.open("rb") as handle:
            response = await client.post(
                f"{http_base}/v1/transcribe",
                headers=headers,
                files={"audio": ("cmd.wav", handle, "audio/wav")},
            )
        if response.status_code >= 400:
            return ""
        return str(response.json().get("text") or "").strip()
    finally:
        try:
            tmp.unlink(missing_ok=True)
            tmp.parent.rmdir()
        except OSError:
            pass
