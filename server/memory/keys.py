"""Preference keys Jarvis is allowed to remember. Secrets are never stored."""

from __future__ import annotations

ALLOWED_PREFERENCE_KEYS = frozenset(
    {
        "default_projects_directory",
        "preferred_language",
        "address_as",
    }
)

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
PATH_TOOLS = frozenset({"list_directory", "create_folder", "create_file", "delete_path"})
PROJECT_PARENT_TOOLS = frozenset({"create_folder", "create_file"})
