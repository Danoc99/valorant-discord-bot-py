from __future__ import annotations
import aiohttp
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from bot.services.matches import Match

BASE = "https://vlrggapi.vercel.app/match?q=upcoming"

def _coerce_dt(val: Any) -> Optional[datetime]:
    """
    Accepts ISO strings like '2025-09-12 13:00:00' or epoch seconds/ms (str/int/float).
    Returns UTC-aware datetime or None.
    """
    if val is None:
        return None
    # epoch numbers (sec or ms)
    if isinstance(val, (int, float)) or (isinstance(val, str) and val.isdigit()):
        ts = float(val)
        if ts > 1_000_000_000_000:  # ms -> s
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    # ISO-ish string
    if isinstance(val, str):
        s = val.strip().replace("T", " ")
        try:
            # Treat as UTC if naive
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except Exception:
            return None
    return None

def _canon_tournament(event_name: str) -> Optional[str]:
    e = (event_name or "").lower()
    # Champions finals event (e.g., "VALORANT Champions 2025")
    if "champions" in e and "champions tour" not in e:
        return "VCT Champions"
    # Masters (Toronto, Shanghai, etc.)
    if "masters" in e:
        return "VCT Masters"
    # VCT regional stages (e.g., "Champions Tour 2025: Americas Stage 2")
    if "champions tour" in e and "americas" in e:
        return "VCT Americas"
    # Ignore Challengers/Game Changers/others for this bot
    return None

async def fetch_upcoming(limit: int = 50) -> List[Match]:
    timeout = aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(timeout=timeout) as sess:
        async with sess.get(BASE) as resp:
            resp.raise_for_status()
            payload = await resp.json()

    segs = (((payload or {}).get("data") or {}).get("segments")) or []
    out: List[Match] = []
    for s in segs:
        # Field names per README
        team1 = (s.get("team1") or "TBD") or "TBD"
        team2 = (s.get("team2") or "TBD") or "TBD"
        stage  = s.get("match_series") or s.get("round_info") or "Stage"
        event  = s.get("match_event") or s.get("tournament_name") or ""
        dt     = _coerce_dt(s.get("unix_timestamp"))

        t = _canon_tournament(event)
        if t is None or dt is None:
            continue

        out.append(Match(
            id=str(s.get("match_page") or f"{team1}-vs-{team2}-{int(dt.timestamp())}"),
            tournament=t,
            stage=stage,
            best_of="BO3",  # VLR upcoming endpoint doesn’t reliably include BoX; default to BO3
            team1=team1,
            team2=team2,
            start_time=dt,
            status="SCHEDULED",
        ))

    out.sort(key=lambda m: m.start_time)
    return out[:limit]
