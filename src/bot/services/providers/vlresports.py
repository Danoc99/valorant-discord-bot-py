from __future__ import annotations
import aiohttp
from datetime import datetime, timedelta, timezone
from typing import List
from bot.services.matches import Match

BASE = "https://vlr.orlandomm.net/api/v1/matches"  # community VLR API

def _canon_tournament(event: str, tournament: str) -> str | None:
    e = (event or "").lower()
    t = (tournament or "").lower()
    blob = f"{e} {t}"

    if "valorant champions" in blob:         # finals event title
        return "VCT Champions"
    if "masters" in blob:                    # Masters Shanghai/Toronto/etc.
        return "VCT Masters"
    if "champions tour" in blob and "americas" in blob:
        return "VCT Americas"
    return None

def _parse_in_to_dt(in_str: str) -> datetime | None:
    if not in_str:
        return None
    s = in_str.strip().lower()
    if s == "live" or "live" in s:
        return datetime.now(timezone.utc)

    total = timedelta()
    num = ""
    for ch in s:
        if ch.isdigit():
            num += ch
            continue
        if num:
            n = int(num)
            if ch == 'w':
                total += timedelta(weeks=n)
            elif ch == 'd':
                total += timedelta(days=n)
            elif ch == 'h':
                total += timedelta(hours=n)
            elif ch == 'm':
                total += timedelta(minutes=n)
            num = ""
    if num:
        total += timedelta(hours=int(num))
    return datetime.now(timezone.utc) + total

async def fetch_upcoming(limit: int = 50) -> List[Match]:
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as sess:
        async with sess.get(BASE) as resp:
            resp.raise_for_status()
            payload = await resp.json()

    items = (payload or {}).get("data") or []
    out: List[Match] = []

    for it in items:
        event = it.get("event") or ""
        tournament = it.get("tournament") or ""

        canon = _canon_tournament(event, tournament)
        if canon is None:
            continue

        teams = it.get("teams") or []
        team1 = (teams[0].get("name") if len(teams) > 0 else "TBD") or "TBD"
        team2 = (teams[1].get("name") if len(teams) > 1 else "TBD") or "TBD"

        # relative "in" (e.g., '1w 2d 3h'), convert to a rough UTC start time
        start_dt = _parse_in_to_dt(it.get("in") or "")
        if not start_dt:
            continue

        status = "LIVE" if ((it.get("in") or "").strip().lower() == "live") else "SCHEDULED"
        mid = str(it.get("id") or f"{team1}-vs-{team2}-{int(start_dt.timestamp())}")

        out.append(Match(
            id=mid,
            tournament=canon,
            stage=tournament or "Stage",
            best_of="BO3",  # this API rarely includes BoX
            team1=team1,
            team2=team2,
            start_time=start_dt,
            status=status,
        ))

    out.sort(key=lambda m: m.start_time)
    return out[:limit]
