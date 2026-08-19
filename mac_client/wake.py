"""Optional Mac-side wake loop: record a clip, ask the brain, then speak the reply."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from server.ai.wake import is_junk_transcript
from server.utils.audio import clip_is_quiet, play_wav, record_microphone
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
    window_seconds: float = 4.0,
    command_seconds: float = 5.0,
    ptt_fallback: bool = True,
    once: bool = False,
) -> None:
    import httpx

    headers = {"X-Jarvis-Token": token}
    timeout = httpx.Timeout(90.0)
    logger.info("wake loop http=%s window=%s — speak into this Mac", http_base, window_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            tmp = Path(tempfile.mkdtemp(prefix="jarvis-wake-")) / "clip.wav"
            try:
                await asyncio.to_thread(record_microphone, tmp, duration_seconds=window_seconds)
                if clip_is_quiet(tmp):
                    continue
                with tmp.open("rb") as handle:
                    response = await client.post(
                        f"{http_base}/v1/wake/audio",
                        headers=headers,
                        files={"audio": ("clip.wav", handle, "audio/wav")},
                        data={"fallback": "true" if ptt_fallback else "false"},
                    )
                response.raise_for_status()
                body = response.json()
                transcript = (body.get("transcript") or body.get("command") or "").strip()
                command = (body.get("command") or "").strip()
                if body.get("heard") and not command:
                    logger.info("heard Jarvis — recording command")
                    command = await _record_command(client, headers, http_base, command_seconds)
                if is_junk_transcript(command):
                    if transcript:
                        logger.info("ignored transcript=%s", transcript[:80])
                    continue
                logger.info("command=%s heard=%s", command[:80], body.get("heard"))
                intent = await client.post(
                    f"{http_base}/v1/intent",
                    headers={**headers, "Content-Type": "application/json"},
                    json={"text": command, "target": "mac"},
                )
                intent.raise_for_status()
                reply = intent.json()
                spoken = (reply.get("spoken_reply") or reply.get("message") or "").strip()
                logger.info(
                    "brain %s spoken_chars=%s",
                    reply.get("type"),
                    len(spoken),
                )
                if spoken:
                    await _play_spoken(client, headers, http_base, spoken)
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
        await asyncio.to_thread(record_microphone, tmp, duration_seconds=seconds)
        if clip_is_quiet(tmp):
            return ""
        with tmp.open("rb") as handle:
            response = await client.post(
                f"{http_base}/v1/transcribe",
                headers=headers,
                files={"audio": ("cmd.wav", handle, "audio/wav")},
            )
        if response.status_code >= 400:
            return ""
        text = str(response.json().get("text") or "").strip()
        return "" if is_junk_transcript(text) else text
    finally:
        try:
            tmp.unlink(missing_ok=True)
            tmp.parent.rmdir()
        except OSError:
            pass


async def _play_spoken(client, headers: dict[str, str], http_base: str, text: str) -> None:
    response = await client.post(
        f"{http_base}/v1/speak",
        headers={**headers, "Content-Type": "application/json"},
        json={"text": text, "play": False},
    )
    response.raise_for_status()
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-say-")) / "reply.wav"
    try:
        tmp.write_bytes(response.content)
        await asyncio.to_thread(play_wav, tmp)
    finally:
        try:
            tmp.unlink(missing_ok=True)
            tmp.parent.rmdir()
        except OSError:
            pass
