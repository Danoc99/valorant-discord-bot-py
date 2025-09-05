from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, Optional

# data/ will live next to src/
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"

def _read() -> Dict[str, Any]:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # Corrupted/empty file → start fresh (defensive coding)
            return {}
    return {}

def _write(data: Dict[str, Any]) -> None:
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

# public helpers

def set_alert_channel(guild_id: int, channel_id: int) -> None:
    """Remember which channel in this guild should get VCT alerts."""
    data = _read()
    g = data.setdefault(str(guild_id), {})
    g["alert_channel_id"] = int(channel_id)
    _write(data)

def get_alert_channel(guild_id: int) -> Optional[int]:
    """Return the saved alert channel id for this guild, or None."""
    data = _read()
    g = data.get(str(guild_id), {})
    cid = g.get("alert_channel_id")
    return int(cid) if cid is not None else None

def mark_alert_sent(guild_id: int, match_id: str) -> None:
    """Record that we've already alerted this match in this guild."""
    data = _read()
    g = data.setdefault(str(guild_id), {})
    sent = set(g.get("alerts_sent", []))
    sent.add(str(match_id))
    g["alerts_sent"] = sorted(sent)
    _write(data)

def was_alert_sent(guild_id: int, match_id: str) -> bool:
    """Check if we've already alerted this match in this guild."""
    data = _read()
    g = data.get(str(guild_id), {})
    return str(match_id) in set(g.get("alerts_sent", []))

def mark_event_created(guild_id: int, match_id: str) -> None:
    data = _read()
    g = data.setdefault(str(guild_id), {})
    created = set(g.get("events_created", []))
    created.add(str(match_id))
    g["events_created"] = sorted(created)
    _write(data)

def was_event_created(guild_id: int, match_id: str) -> bool:
    data = _read()
    g = data.get(str(guild_id), {})
    return str(match_id) in set(g.get("events_created", []))

# ---------- per-guild settings (with sensible defaults) ----------

def _guild(data, guild_id: int):
    return data.setdefault(str(guild_id), {})

def get_lead_minutes(guild_id: int, default: int = 30) -> int:
    data = _read()
    g = data.get(str(guild_id), {})
    return int(g.get("lead_minutes", default))

def set_lead_minutes(guild_id: int, minutes: int) -> None:
    minutes = max(5, min(180, int(minutes)))  # clamp 5..180
    data = _read()
    g = _guild(data, guild_id)
    g["lead_minutes"] = minutes
    _write(data)

def is_event_enabled(guild_id: int, default: bool = True) -> bool:
    data = _read()
    g = data.get(str(guild_id), {})
    return bool(g.get("event_enabled", default))

def set_event_enabled(guild_id: int, enabled: bool) -> None:
    data = _read()
    g = _guild(data, guild_id)
    g["event_enabled"] = bool(enabled)
    _write(data)
