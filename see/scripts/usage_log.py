"""Privacy-conscious JSON Lines usage log for see."""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path


MAX_LINES = 5000
_LOCK = threading.Lock()
_SECRET_KEY_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|authorization|password|credential)"
)
_SECRET_VALUE_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|token|authorization)\s*[=:]\s*"
    r"(?:\S+\s+)?[^\s,;]+|\bbearer\s+[^\s,;]+"
)


def _redact(fields: dict[str, object]) -> dict[str, object]:
    """Keep the log diagnostic-only; never persist keys or bearer tokens."""
    result: dict[str, object] = {}
    for key, value in fields.items():
        if _SECRET_KEY_RE.search(str(key)):
            result[key] = "***"
            continue
        if isinstance(value, str):
            result[key] = _SECRET_VALUE_RE.sub("***", value)
        else:
            result[key] = value
    return result


def log_file_path() -> Path:
    override = os.getenv("SEE_LOG_FILE", "").strip()
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        root = Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    else:
        root = Path(os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return root / "see" / "usage.log"


def append(event: str, **fields: object) -> Path:
    """Append one usage record. Never receives API keys or raw media content."""
    record: dict[str, object] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": event,
        **_redact(fields),
    }
    path = log_file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            try:
                path.parent.chmod(0o700)
            except OSError:
                pass
        line = json.dumps(record, ensure_ascii=False)
        with _LOCK:
            existing = (
                path.read_text(encoding="utf-8", errors="ignore").splitlines()
                if path.exists()
                else []
            )
            existing.append(line)
            if len(existing) > MAX_LINES:
                existing = existing[-MAX_LINES:]
            temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
            temporary.write_text("\n".join(existing) + "\n", encoding="utf-8")
            if os.name != "nt":
                try:
                    temporary.chmod(0o600)
                except OSError:
                    pass
            os.replace(temporary, path)
    except OSError:
        # A diagnostics log must never block the actual recognition flow.
        return path
    return path


def read(limit: int = 200) -> list[dict[str, object]]:
    path = log_file_path()
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    entries: list[dict[str, object]] = []
    for line in lines[-limit:]:
        try:
            parsed = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            entries.append(parsed)
    return entries


def clear() -> bool:
    path = log_file_path()
    if path.exists():
        try:
            path.unlink()
            return True
        except OSError:
            return False
    return False
