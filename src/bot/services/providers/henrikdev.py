from __future__ import annotations
import os, json
from datetime import datetime, timezone
from typing import List, Dict, Any
import aiohttp

from bot.services.matches import Match  # your dataclass

API_KEY = (os.getenv("HENRIKDEV_API_KEY") or "").strip()
BASE = "https://api.henrikdev.xyz/valorant/v1/esports/schedule"

# We want these leagues
LEAGUES = ["vct_americas", "masters", "champions"]
LEAGUE_NAME = {
    "vct_americas": "VCT Americas",
    "masters": "VCT Masters",
    "champions": "VCT Champions",
}

def _coerce_datetime(val) -> datetime | None:
    """Accept ISO string, epoch seconds, or epoch milliseconds."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        ts = float(val)
        if ts > 1_000_000_000_000:  # ms → s
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(val, str) and val:
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            try:
                num = float(val)
                return _coerce_datetime(num)
            except Exception:
                return None
    return None

def _deep_find_dt(obj) -> datetime | None:
    """Depth-first search for a datetime-like value under keys containing date/start/time."""
    stack = [obj]
    seen = set()
    while stack:
        cur = stack.pop()
        if id(cur) in seen:
            continue
        seen.add(id(cur))
        if isinstance(cur, dict):
            for k, v in cur.items():
                kl = (k or "").lower()
                if any(tok in kl for tok in ("date", "start", "time")):
                    dt = _coerce_datetime(v)
                    if dt:
                        return dt
                if isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)
    return None

def _pick_start_dt(it: Dict[str, Any]) -> datetime | None:
    """Try common places, then deep-search as a last resort."""
    # Common root-level keys (string ISO or epoch)
    for k in ("date", "start_time", "startTime", "start", "time", "epoch", "epochMillis", "startMillis"):
        dt = _coerce_datetime(it.get(k))
        if dt:
            return dt
    # Nested under 'match'
    m = it.get("match") or {}
    for k in ("start_time", "startTime", "start", "time", "epoch", "epochMillis", "startMillis"):
        dt = _coerce_datetime(m.get(k))
        if dt:
            return dt
    # Nested under 'tournament'
    t = it.get("tournament") or {}
    for k in ("start_time", "startTime", "start", "time", "epoch", "epochMillis", "startMillis"):
        dt = _coerce_datetime(t.get(k))
        if dt:
            return dt
    # Last resort: deep search anywhere
    return _deep_find_dt(it)

def _pick_state(it: Dict[str, Any]) -> str:
    """Prefer 'state' but fall back to 'status' (root or nested)."""
    state = it.get("state") or it.get("status")
    if not state:
        m = it.get("match") or {}
        state = m.get("state") or m.get("status")
    return str(state or "").lower()

def _team_name(obj: Dict[str, Any]) -> str:
    """Team name from multiple shapes."""
    return (
        obj.get("name")
        or (obj.get("team") or {}).get("name")
        or obj.get("code")           # e.g., “C9”
        or obj.get("abbr")
        or obj.get("short")
        or "TBD"
    )



def _convert(items: List[Dict[str, Any]]) -> List[Match]:
    def _canon_tournament(league_id: str | None, league_name: str | None) -> str | None:
        # Exact identifier first
        if league_id in LEAGUE_NAME:
            return LEAGUE_NAME[league_id]
        # Fuzzy on display name
        name = (league_name or "").lower()
        if "americas" in name and "vct" in name:
            return "VCT Americas"
        if "masters" in name:
            return "VCT Masters"
        if "champions" in name:
            return "VCT Champions"
        return None

    counts = {"total": 0, "not_match_type": 0, "not_vct": 0, "no_start": 0, "completed": 0, "added": 0}

    out: List[Match] = []
    now = datetime.now(timezone.utc)

    for it in items:
        counts["total"] += 1

        # If 'type' exists and is clearly not a match-like item, skip
        it_type = (it.get("type") or "").lower()
        if it_type and it_type not in ("match", "game", "series"):
            counts["not_match_type"] += 1
            continue

        league_obj = it.get("league") or {}
        tournament = _canon_tournament(
            league_obj.get("identifier"),
            league_obj.get("name"),
        )
        if tournament is None:
            counts["not_vct"] += 1
            continue

        start = _pick_start_dt(it)
        if not start:
            counts["no_start"] += 1
            continue

        state = _pick_state(it)
        if state == "completed":
            counts["completed"] += 1
            continue

        match_info = it.get("match") or {}
        teams = match_info.get("teams") or []

        # Try common shapes: teams list, or blue/red, or team1/team2
        team1 = _team_name(teams[0]) if len(teams) > 0 else None
        team2 = _team_name(teams[1]) if len(teams) > 1 else None
        if not team1 or not team2:
            blue = match_info.get("blue") or match_info.get("team1") or {}
            red  = match_info.get("red")  or match_info.get("team2") or {}
            team1 = team1 or _team_name(blue)
            team2 = team2 or _team_name(red)

        out.append(Match(
            id=str(match_info.get("id") or f"{team1}-vs-{team2}-{int(start.timestamp())}"),
            tournament=tournament,
            stage=(it.get("tournament") or {}).get("name") or "Stage",
            best_of=_best_of(match_info.get("game_type")),
            team1=team1 or "TBD",
            team2=team2 or "TBD",
            start_time=start,
            status=("LIVE" if ("progress" in state or "live" in state) else "SCHEDULED"),
        ))
        counts["added"] += 1

    # One-line summary (dev only; safe to keep for now)
    print(f"convert_summary: total={counts['total']} not_match_type={counts['not_match_type']} "
          f"not_vct={counts['not_vct']} no_start={counts['no_start']} completed={counts['completed']} "
          f"added={counts['added']}")
    return out




async def _get_json(sess: aiohttp.ClientSession, params: Any) -> Dict[str, Any]:
    async with sess.get(BASE, params=params) as resp:
        # TEMP debug so you can see repeated keys in the final URL
        print("GET", str(resp.url))
        text = await resp.text()
        if resp.status != 200:
            resp.raise_for_status()
        return json.loads(text)

async def fetch_schedule(limit: int = 50) -> List[Match]:
    if not API_KEY:
        raise RuntimeError("HENRIKDEV_API_KEY missing in environment")

    headers = {
        "Authorization": API_KEY,           # docs: plain key in Authorization header
        "Accept": "application/json",
        "User-Agent": "valorant-bot/0.1 (+local-dev)"
    }
    timeout = aiohttp.ClientTimeout(total=10)

    # Try filtered first; fall back to simpler shapes if needed
    query_variants = [
    # Champions — most important for you right now
    [("league", "champions"), ("region", "international")],
    [("league", "champions")],

    # Masters (international)
    [("league", "masters"), ("region", "international")],
    [("league", "masters")],

    # Americas (regional)
    [("league", "vct_americas"), ("region", "north america")],
    [("league", "vct_americas")],

    # All three with repeated keys
    [("league", "vct_americas"), ("league", "masters"), ("league", "champions")],

    # last resort: no filter
    {},  # aiohttp will just not add any query
]

    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as sess:
        last_err: Exception | None = None
        for params in query_variants:
            try:
                payload = await _get_json(sess, params)
                items = payload.get("data") or []
                print("raw_count:", len(items))
                print("raw_sample_leagues:", sorted({
                    (it.get("league") or {}).get("identifier") for it in items if it.get("type") == "match"
                })[:10])
                data = (payload.get("data") or [])
                # Convert and sort
                matches = _convert(data)
                live = [m for m in matches if m.status == "LIVE"]
                upcoming = sorted([m for m in matches if m.status != "LIVE"], key=lambda m: m.start_time)
                return (live + upcoming)[:limit]
            except Exception as e:
                last_err = e
                continue

        # If all variants failed, surface the last error
        raise last_err if last_err else RuntimeError("Unknown error in fetch_schedule")
