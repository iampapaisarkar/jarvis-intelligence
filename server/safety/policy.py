"""Lexical path and command policy. Safety is not delegated to the LLM."""

from __future__ import annotations

import posixpath
import re
from typing import Literal

Target = Literal["windows", "mac"]

_DENIED_SPOKEN = "I can't do that. That action is blocked by safety policy."

_WINDOWS_SYSTEM_PREFIXES = (
    "c:/windows",
    "c:/program files",
    "c:/program files (x86)",
    "c:/programdata",
    "c:/system volume information",
    "c:/recovery",
    "c:/boot",
    "c:/$recycle.bin",
    "c:/perflogs",
)

_UNIX_SYSTEM_PREFIXES = (
    "/system",
    "/usr",
    "/bin",
    "/sbin",
    "/etc",
    "/dev",
    "/proc",
    "/sys",
    "/var",
    "/private",
    "/library",
    "/cores",
    "/boot",
    "/root",
)

_CREDENTIAL_PARTS = {
    ".ssh",
    ".gnupg",
    ".aws",
    ".azure",
    ".gcloud",
    ".kube",
    ".docker",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "shadow",
    "ntds.dit",
    "sam",
    "wallet.dat",
    ".netrc",
    "credentials.json",
    "credentials",
}

_CREDENTIAL_SUFFIXES = (".pem", ".pfx", ".p12", ".key")

# Independently rejected even if the user confirms.
_FORBIDDEN_COMMAND = re.compile(
    "|".join(
        (
            r"\bformat\s+[a-z]:",
            r"\bdiskpart\b",
            r"\bmkfs\b",
            r"\bdd\s+if=",
            r"\brm\s+-rf\s+/(\s|$|\*)",
            r"\bdel\s+/[sfq]+\s+[a-z]:\\",
            r"\bcipher\s+/w",
            r"\bbcdedit\b",
            r"\bbootrec\b",
            r"\\\\\.\\physicaldrive",
            r"/dev/sd[a-z]",
            r"/dev/disk",
            r"\bnetsh\s+advfirewall\b",
            r"\bufw\s+disable\b",
            r"\biptables\b",
            r"\bSet-MpPreference\b",
            r"\bDisableAntiSpyware\b",
            r"\bsc\s+stop\s+windefend\b",
            r"\bcurl\b.+\|\s*(?:ba)?sh\b",
            r"\bwget\b.+\|\s*(?:ba)?sh\b",
            r"\biex\s*\(",
            r"\bInvoke-Expression\b",
            r"\bInvoke-WebRequest\b",
            r"\bpowershell\s+-[eE]nc",
            r"\bpython3?\s+-c\b",
            r"\bperl\s+-e\b",
            r"\bchmod\s+-R\s+777\s+/",
            r"\bchown\s+-R\b.+\s+/",
            r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;",
            r"\breg\s+delete\b",
            r"\bnet\s+user\b",
            r"system32",
            r"%systemroot%",
            r"syswow64",
        )
    ),
    re.IGNORECASE,
)

_DOWNLOAD_EXE = re.compile(
    r"(?i)(downloads|temp|tmp|appdata).+\.(exe|msi|bat|cmd|ps1|scr|com|dll)$"
)


def denied_spoken() -> str:
    return _DENIED_SPOKEN


def normalize_path(path: str, target: Target) -> str:
    raw = (path or "").strip().replace("\\", "/")
    if not raw:
        return ""
    if raw.startswith("~"):
        home = "c:/users/user" if target == "windows" else "/users/user"
        raw = home + raw[1:]
    if target == "windows":
        raw = raw.lower()
        raw = re.sub(r"%[a-z0-9_]+%", "", raw)
    else:
        raw = raw.replace("//", "/")
    absolute = raw.startswith("/") or (len(raw) >= 2 and raw[1] == ":")
    collapsed = posixpath.normpath(raw)
    if target == "windows":
        collapsed = collapsed.lower().replace("\\", "/")
        if collapsed.startswith("//"):
            collapsed = "/" + collapsed.lstrip("/")
    if absolute and collapsed in {".", ""}:
        return "/" if target != "windows" else "c:/"
    return collapsed


def path_parts(normalized: str) -> tuple[str, ...]:
    trimmed = normalized.strip("/")
    if not trimmed:
        return tuple()
    return tuple(part.lower() for part in trimmed.split("/") if part)


def is_windows_drive_root(normalized: str) -> bool:
    return bool(re.fullmatch(r"[a-z]:/?", normalized))


def is_unix_root(normalized: str) -> bool:
    return normalized in {"/", ""}


def has_credential_marker(normalized: str) -> bool:
    parts = path_parts(normalized)
    lowered = normalized.lower()
    if any(part in _CREDENTIAL_PARTS for part in parts):
        return True
    if lowered.endswith(_CREDENTIAL_SUFFIXES):
        return True
    if lowered.endswith("/.env") or lowered.endswith(".env"):
        return True
    return False


def is_system_path(path: str, target: Target, *, destructive: bool) -> bool:
    normalized = normalize_path(path, target)
    if not normalized:
        return True
    if has_credential_marker(normalized):
        return True
    if target == "windows":
        if is_windows_drive_root(normalized):
            return True
        if normalized.startswith("//") or normalized.startswith("\\\\"):
            return True
        return any(
            normalized == prefix or normalized.startswith(prefix + "/")
            for prefix in _WINDOWS_SYSTEM_PREFIXES
        )
    if is_unix_root(normalized):
        return True
    if destructive and (
        normalized == "/applications" or normalized.startswith("/applications/")
    ):
        return True
    return any(
        normalized == prefix or normalized.startswith(prefix + "/")
        for prefix in _UNIX_SYSTEM_PREFIXES
    )


def is_ambiguous_path(path: str) -> bool:
    cleaned = path.strip().replace("\\", "/")
    if cleaned in {".", "..", "./", "../"}:
        return True
    if cleaned.startswith("~") or cleaned.startswith("/") or (len(cleaned) >= 2 and cleaned[1] == ":"):
        return False
    return "/" not in cleaned


def command_is_forbidden(command: str) -> bool:
    text = " ".join((command or "").split())
    if not text:
        return True
    if _FORBIDDEN_COMMAND.search(text):
        return True
    if re.search(r"(?i)\brm\s+-rf\s+/(etc|usr|bin|sbin|system|windows)\b", text):
        return True
    return False


def application_is_forbidden(name: str) -> bool:
    cleaned = name.strip().replace("\\", "/")
    if _DOWNLOAD_EXE.search(cleaned):
        return True
    lowered = cleaned.lower()
    if lowered.endswith((".exe", ".msi", ".bat", ".cmd", ".ps1", ".scr")) and (
        "/" in cleaned or "\\" in name
    ):
        return True
    return False
