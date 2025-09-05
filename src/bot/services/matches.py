from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List

@dataclass
class Match:
    id: str
    tournament: str          # "VCT Americas" | "VCT Masters" | "VCT Champions"
    stage: str               # e.g., "Swiss Stage: Round 1"
    best_of: str             # e.g., "BO3"
    team1: str
    team2: str
    start_time: datetime     # UTC
    status: str              # "LIVE" | "SCHEDULED"

VCT_TOURNAMENTS = {"VCT Americas", "VCT Masters", "VCT Champions"}

# ---- mock fallback (if API is down) ----
def _utc_in(minutes: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)

def _mock_vct_data() -> List[Match]:
    return [
        Match(
            id="G2-vs-T1-FAKE",
            tournament="VCT Masters",
            stage="Swiss Stage: Round 1",
            best_of="BO3",
            team1="G2 Esports",
            team2="T1",
            start_time=_utc_in(-15),
            status="LIVE",
        ),
        Match(
            id="C9-vs-NRG-FAKE",
            tournament="VCT Americas",
            stage="Regular Season: Week 1",
            best_of="BO3",
            team1="Cloud9",
            team2="NRG",
            start_time=_utc_in(120),
            status="SCHEDULED",
        ),
    ]

# ---- public API used by your cogs/poller ----
async def upcoming_vct_matches(limit: int = 10) -> List[Match]:
    # 0) Official-site fallback (SSR HTML JSON). Put this FIRST so we see future Champions.
    try:
        from bot.services.providers.valorant_official import fetch_upcoming as fetch_official
        off = await fetch_official(limit=limit * 2)
        off = [m for m in off if m.tournament in VCT_TOURNAMENTS]
        print("official_first_count:", len(off))
        if off:
            live = [m for m in off if m.status == "LIVE"]
            upcoming = sorted([m for m in off if m.status != "LIVE"], key=lambda m: m.start_time)
            return (live + upcoming)[:limit]
    except Exception as e:
        print("official_site provider failed; will try HenrikDev:", e)

    # 1) HenrikDev (sometimes only returns completed far ahead of events)
    try:
        from bot.services.providers.henrikdev import fetch_schedule
        data = await fetch_schedule(limit=limit * 2)
        print("provider_count:", len(data), "tournaments:", sorted({m.tournament for m in data})[:10])
        data = [m for m in data if m.tournament in VCT_TOURNAMENTS]
        print("after_filter_count:", len(data))
        if data:
            live = [m for m in data if m.status == "LIVE"]
            upcoming = sorted([m for m in data if m.status != "LIVE"], key=lambda m: m.start_time)
            return (live + upcoming)[:limit]
    except Exception as e:
        print("henrikdev error; will try vlrggapi:", e)

    # 2) vlrggapi fallback
    try:
        from bot.services.providers.vlrggapi import fetch_upcoming as fetch_vlrgg
        vlr1 = await fetch_vlrgg(limit=limit * 2)
        print("vlr_fallback_count:", len(vlr1))
        vlr1 = [m for m in vlr1 if m.tournament in VCT_TOURNAMENTS]
        if vlr1:
            return vlr1[:limit]
    except Exception as e:
        print("vlrggapi fallback failed; trying vlresports:", e)

    # 3) vlresports fallback
    try:
        from bot.services.providers.vlresports import fetch_upcoming as fetch_vlr2
        vlr2 = await fetch_vlr2(limit=limit * 2)
        print("vlresports_fallback_count:", len(vlr2))
        vlr2 = [m for m in vlr2 if m.tournament in VCT_TOURNAMENTS]
        if vlr2:
            return vlr2[:limit]
    except Exception as e:
        print("vlresports fallback failed; using mock:", e)

    # 4) Last resort
    data = _mock_vct_data()
    live = [m for m in data if m.status == "LIVE"]
    upcoming = sorted([m for m in data if m.status != "LIVE"], key=lambda m: m.start_time)
    return (live + upcoming)[:limit]


