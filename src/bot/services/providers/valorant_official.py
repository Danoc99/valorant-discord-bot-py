from __future__ import annotations
import re, json, aiohttp
from datetime import datetime, timezone
from typing import Any, Dict, List

from bot.services.matches import Match  # your @dataclass

# We’ll read the official schedule page (SSR HTML includes a big JSON blob).
# Keep it in English to simplify parsing.
SCHEDULE_URL = (
    "https://valorantesports.com/en-US/leagues/"
    "champions%2Cvct_masters%2Cvct_americas"
)

# Regex to capture the embedded Next.js data blob
_NEXT_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
    re.S | re.I,
)

# Map human/loose names we find in that JSON to our normalized tournaments
def _canon_tournament(name: str | None) -> str | None:
    n = (name or "").lower()
    if "champions" in n:
        return "VCT Champions"
    if "masters" in n:
        return "VCT Masters"
    if "americas" in n and "vct" in n:
        return "VCT Americas"
    return None

def _coerce_datetime(val: Any) -> datetime | None:
    """Accept ISO string or epoch (seconds/ms) and return UTC datetime."""
    if val is None:
        return None
    # Epoch int/float?
    if isinstance(val, (int, float)):
        ts = float(val)
        if ts > 1_000_000_000_000:  # ms → s
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    # String?
    if isinstance(val, str) and val:
        s = val.strip()
        # Try ISO first
        try:
            # Handle trailing "Z"
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return datetime.fromisoformat(s).astimezone(timezone.utc)
        except Exception:
            # Try integer-looking strings
            try:
                num = float(s)
                return _coerce_datetime(num)
            except Exception:
                return None
    return None

def _walk(obj: Any):
    """Yield dicts from a deeply nested JSON structure."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _walk(it)

def _maybe_team_name(team_obj: Dict[str, Any]) -> str | None:
    return (
        team_obj.get("name")
        or (team_obj.get("team") or {}).get("name")
        or team_obj.get("code")
        or team_obj.get("abbr")
        or None
    )

def _extract_matches_from_next_data(data: Dict[str, Any]) -> List[Match]:
    """
    Heuristic extractor:
    Find dicts containing:
      - league/tournament name
      - teams (list/dict)
      - start time (start/startTime/date/epoch…)
    and normalize into our Match model.
    """
    out: List[Match] = []
    now = datetime.now(timezone.utc)

    for node in _walk(data):
        # Find a league/tournament name in typical places
        league_name = None
        league_obj = node.get("league") or {}
        league_name = (
            league_obj.get("name")
            or node.get("leagueName")
            or (node.get("tournament") or {}).get("name")
            or node.get("event")
        )

        canon = _canon_tournament(league_name)
        if not canon:
            continue  # not one of our three

        # Find start time in common keys (string ISO or epoch)
        start_val = (
            node.get("startTime")
            or node.get("start")
            or node.get("date")
            or node.get("time")
            or node.get("epoch")
            or node.get("epochMillis")
            or (node.get("match") or {}).get("startTime")
        )
        start = _coerce_datetime(start_val)
        if not start:
            continue

        # Determine match/teams container
        teams = node.get("teams")
        if teams is None and "match" in node:
            teams = (node.get("match") or {}).get("teams")

        # Normalize two team names
        team1 = team2 = None
        if isinstance(teams, list) and len(teams) >= 2:
            team1 = _maybe_team_name(teams[0])
            team2 = _maybe_team_name(teams[1])
        elif isinstance(teams, dict):
            # Sometimes teams are under blue/red or team1/team2
            blue = teams.get("blue") or teams.get("team1") or {}
            red  = teams.get("red")  or teams.get("team2") or {}
            team1 = _maybe_team_name(blue)
            team2 = _maybe_team_name(red)

        if not team1 or not team2:
            continue

        # Stage / best-of (best effort)
        stage = (
            (node.get("tournament") or {}).get("stage")
            or (node.get("stage") or {}).get("name")
            or (node.get("tournament") or {}).get("name")
            or "Stage"
        )

        # Various shapes store Bo count in different spots
        bo = None
        game_type = node.get("game_type") or {}
        bo = (
            node.get("bestOf")
            or node.get("bo")
            or game_type.get("count")
        )
        try:
            bo_int = int(bo) if bo is not None else 3
        except Exception:
            bo_int = 3
        best_of = f"BO{bo_int}"

        # Status (we only care about upcoming/live)
        state = str(node.get("state") or node.get("status") or "").lower()
        if "completed" in state or "final" in state:
            continue
        status = "LIVE" if ("live" in state or "progress" in state) else ("SCHEDULED" if start >= now else "SCHEDULED")

        match_id = (
            str((node.get("match") or {}).get("id"))
            or f"{team1}-vs-{team2}-{int(start.timestamp())}"
        )

        out.append(Match(
            id=match_id,
            tournament=canon,        # "VCT Champions" | "VCT Masters" | "VCT Americas"
            stage=stage,
            best_of=best_of,
            team1=team1,
            team2=team2,
            start_time=start,
            status=status,
        ))

    # Sort: LIVE first, then upcoming soonest
    live = [m for m in out if m.status == "LIVE"]
    upcoming = sorted([m for m in out if m.status != "LIVE"], key=lambda m: m.start_time)
    print(f"official_site_count: {len(out)}")
    return live + upcoming


async def fetch_upcoming(limit: int = 50) -> List[Match]:
    """Download the official schedule page and extract Champions/Masters/Americas."""
    timeout = aiohttp.ClientTimeout(total=12)
    headers = {
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": "valorant-bot/0.1 (+local-dev)"
    }
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as sess:
        async with sess.get(SCHEDULE_URL) as resp:
            html = await resp.text()

    m = _NEXT_RE.search(html)
    if not m:
        # If we fail to find Next.js data, bail (caller will try other providers)
        print("official_site: __NEXT_DATA__ not found")
        return []

    try:
        data = json.loads(m.group(1))
    except Exception as e:
        print("official_site: JSON parse error:", e)
        return []

    matches = _extract_matches_from_next_data(data)
    return matches[:limit]
