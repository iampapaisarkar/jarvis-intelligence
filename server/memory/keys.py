"""Preference keys Jarvis is allowed to remember. Secrets are never stored."""

from __future__ import annotations

ALLOWED_PREFERENCE_KEYS = frozenset(
    {
        "default_projects_directory",
        "preferred_language",
        "address_as",
        "owner_name",
        "owner_email",
        "owner_phone",
        "owner_address",
        "spouse_name",
        "child_name",
    }
)

PREFERENCE_LABELS = {
    "default_projects_directory": "your projects folder",
    "preferred_language": "your preferred language",
    "address_as": "how to address you",
    "owner_name": "your name",
    "owner_email": "your email",
    "owner_phone": "your phone number",
    "owner_address": "your address",
    "spouse_name": "your wife's name",
    "child_name": "your son's name",
}

PATH_PREFERENCE_KEYS = frozenset({"default_projects_directory"})

ALIAS_KINDS = frozenset({"application", "path"})

DEFAULT_PATH_ALIASES = (
    ("downloads", "~/Downloads"),
    ("documents", "~/Documents"),
    ("desktop", "~/Desktop"),
    ("projects", "~/Projects"),
)

DEFAULT_PROJECTS_DIRECTORY = "~/Projects"

BRAIN_LOCAL_TOOLS = frozenset({"remember_preference"})
PATH_TOOLS = frozenset({"list_directory", "create_folder", "create_file", "delete_path", "open_path"})
PROJECT_PARENT_TOOLS = frozenset({"create_folder", "create_file", "open_path"})
OWNER_SETTING_MAP = (
    ("jarvis_owner_name", "owner_name"),
    ("jarvis_owner_email", "owner_email"),
    ("jarvis_owner_phone", "owner_phone"),
    ("jarvis_owner_address", "owner_address"),
    ("jarvis_spouse_name", "spouse_name"),
    ("jarvis_child_name", "child_name"),
)
