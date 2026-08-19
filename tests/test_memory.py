from server.config import get_settings
from server.memory.phrases import extract_remember_preference
from server.memory.resolve import enrich_intent, is_bare_name
from server.memory.store import MemoryStore
from server.ai.intent import ParsedIntent


def test_extract_projects_directory_phrase():
    caught = extract_remember_preference("My projects are normally inside ~/Projects.")
    assert caught == {"key": "default_projects_directory", "value": "~/Projects"}


def test_extract_ignores_unrelated_text():
    assert extract_remember_preference("Open VS Code") is None


def test_seed_preferences_and_path_aliases(tmp_path):
    store = MemoryStore(tmp_path / "mem.sqlite", history_limit=20)
    try:
        assert store.get_preference("default_projects_directory") == "~/Projects"
        names = {item["name"] for item in store.list_aliases(kind="path")}
        assert "downloads" in names
        assert store.resolve_path("Downloads", join_projects=False) == "~/Downloads"
        assert store.resolve_path("TestApp", join_projects=True) == "~/Projects/TestApp"
        assert store.resolve_path("~/Documents/x", join_projects=True) == "~/Documents/x"
    finally:
        store.close()


def test_history_is_capped(tmp_path):
    store = MemoryStore(tmp_path / "mem.sqlite", history_limit=20)
    try:
        for i in range(25):
            store.record_task(
                session_id="s",
                tool="get_system_info",
                target="mac",
                arguments={},
                spoken="ok",
                reason="executed",
                executed=True,
            )
        assert len(store.list_history(limit=100)) == 20
    finally:
        store.close()


def test_unknown_preference_key_rejected(tmp_path):
    store = MemoryStore(tmp_path / "mem.sqlite")
    try:
        try:
            store.set_preference("api_token", "secret")
            assert False, "expected ValueError"
        except ValueError:
            pass
    finally:
        store.close()


def test_enrich_create_folder_uses_projects_parent(tmp_path):
    store = MemoryStore(tmp_path / "mem.sqlite")
    try:
        intent = ParsedIntent(
            type="tool_call",
            message="Creating TestApp.",
            spoken_reply="Creating TestApp.",
            session_id="s",
            tool="create_folder",
            target="windows",
            arguments={"path": "TestApp"},
            risk="medium",
            requires_confirmation=True,
        )
        enriched = enrich_intent(intent, store)
        assert enriched.arguments["path"] == "~/Projects/TestApp"
        assert is_bare_name("TestApp") is True
        assert is_bare_name("~/Projects/TestApp") is False
    finally:
        store.close()


def test_enrich_application_alias(tmp_path):
    store = MemoryStore(tmp_path / "mem.sqlite")
    try:
        store.set_alias("editor", "application", "Visual Studio Code")
        intent = ParsedIntent(
            type="tool_call",
            message="Opening editor.",
            spoken_reply="Opening editor.",
            session_id="s",
            tool="open_application",
            target="mac",
            arguments={"application": "editor"},
            risk="low",
            requires_confirmation=False,
        )
        enriched = enrich_intent(intent, store)
        assert enriched.arguments["application"] == "Visual Studio Code"
    finally:
        store.close()
