"""LAN UDP discovery so the Mac body can find the Windows brain without a typed IP."""

from __future__ import annotations

import json
import socket
import threading
from typing import Optional

from server import __version__
from server.utils.logger import get_logger

logger = get_logger("jarvis.discovery")

PROBE = b"JARVIS_DISCOVER"
REPLY_TYPE = "jarvis_brain"
DEFAULT_DISCOVERY_PORT = 8766


def encode_reply(*, ws_port: int, version: str) -> bytes:
    return json.dumps({"type": REPLY_TYPE, "port": ws_port, "version": version}).encode("utf-8")


def decode_reply(raw: bytes) -> Optional[dict]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("type") != REPLY_TYPE:
        return None
    port = data.get("port")
    if not isinstance(port, int) or port < 1 or port > 65535:
        return None
    return data


def broadcast_targets() -> list[str]:
    hosts = ["255.255.255.255", "127.0.0.1"]
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM):
            ip = info[4][0]
            if ip.startswith("127."):
                continue
            parts = ip.split(".")
            if len(parts) == 4:
                hosts.append(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
    except OSError:
        pass
    return list(dict.fromkeys(hosts))


def discover_brain(*, port: int = DEFAULT_DISCOVERY_PORT, timeout: float = 1.5, attempts: int = 3) -> Optional[str]:
    """Return ws://host:port/v1/mac or None."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        sock.bind(("", 0))
        targets = [(host, port) for host in broadcast_targets()]
        for _ in range(max(1, attempts)):
            for target in targets:
                try:
                    sock.sendto(PROBE, target)
                except OSError:
                    continue
            try:
                raw, addr = sock.recvfrom(2048)
            except TimeoutError:
                continue
            except socket.timeout:
                continue
            payload = decode_reply(raw)
            if payload is None:
                continue
            host = addr[0]
            ws_port = int(payload["port"])
            url = f"ws://{host}:{ws_port}/v1/mac"
            logger.info("discovered brain at %s", url)
            return url
    finally:
        sock.close()
    return None


class DiscoveryServer:
    def __init__(self, *, listen_port: int, ws_port: int) -> None:
        self._listen_port = listen_port
        self._ws_port = ws_port
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None

    def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", self._listen_port))
        sock.settimeout(0.5)
        self._sock = sock
        self._thread = threading.Thread(target=self._loop, name="jarvis-discovery", daemon=True)
        self._thread.start()
        logger.info("discovery listening udp/%s", self._listen_port)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _loop(self) -> None:
        assert self._sock is not None
        reply = encode_reply(ws_port=self._ws_port, version=__version__)
        while not self._stop.is_set():
            try:
                raw, addr = self._sock.recvfrom(2048)
            except TimeoutError:
                continue
            except socket.timeout:
                continue
            except OSError:
                if self._stop.is_set():
                    return
                continue
            if raw.strip() != PROBE:
                continue
            try:
                self._sock.sendto(reply, addr)
            except OSError:
                continue
