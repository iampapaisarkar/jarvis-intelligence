from server.discovery import DiscoveryServer, decode_reply, discover_brain, encode_reply


def test_encode_decode_reply():
    raw = encode_reply(ws_port=8765, version="0.9.0")
    payload = decode_reply(raw)
    assert payload is not None
    assert payload["port"] == 8765
    assert payload["type"] == "jarvis_brain"


def test_decode_rejects_junk():
    assert decode_reply(b"not-json") is None
    assert decode_reply(b'{"type":"nope","port":8765}') is None


def test_discover_finds_local_listener():
    server = DiscoveryServer(listen_port=18766, ws_port=8765)
    server.start()
    try:
        url = discover_brain(port=18766, timeout=0.8, attempts=3)
        assert url is not None
        assert url.endswith(":8765/v1/mac")
        assert url.startswith("ws://")
    finally:
        server.stop()
