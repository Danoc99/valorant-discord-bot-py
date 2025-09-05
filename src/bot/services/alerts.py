from __future__ import annotations
import asyncio
import importlib
from math import ceil
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord

# Hot-reloadable matches module + type
from bot.services import matches as matches_module
from bot.services.matches import Match

# Storage helpers (per-guild settings + dedupe)
from bot.services.storage import (
    get_alert_channel,
    was_alert_sent, mark_alert_sent,
    was_event_created, mark_event_created,
    get_lead_minutes, is_event_enabled,
)

# ---- Config ----
DEFAULT_LEAD_MINUTES = 30          # fallback if no per-guild setting
POLL_INTERVAL_SECONDS = 10        # set to 10 while developing

# ---- Styling per tournament (match your /vct_matches cog) ----
TOURNAMENT_STYLE = {
    "VCT Masters":   {"emoji": "🟣", "color": discord.Color.dark_purple()},
    "VCT Americas":  {"emoji": "🟠", "color": discord.Color.orange()},
    "VCT Champions": {"emoji": "🏆", "color": discord.Color.gold()},
}

def _tour_emoji(tournament: str) -> str:
    return TOURNAMENT_STYLE.get(tournament, {}).get("emoji", "🎮")

def _tour_color(tournament: str) -> discord.Color:
    return TOURNAMENT_STYLE.get(tournament, {}).get("color", discord.Color.blurple())

# ---- Formatting helpers ----
def _discord_relative(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return f"<t:{int(ts.timestamp())}:R>"

def _match_embed(m: Match, lead_minutes: int) -> discord.Embed:
    """Styled alert embed showing actual minutes remaining + lead window."""
    emoji = _tour_emoji(m.tournament)
    color = _tour_color(m.tournament)

    now = datetime.now(timezone.utc)
    minutes_left = max(1, ceil((m.start_time - now).total_seconds() / 60.0))

    title_line = f"**{m.team1} vs {m.team2}**"
    details = f"{m.tournament} • {m.stage} • {m.best_of}"
    when = f"Starts {_discord_relative(m.start_time)}"

    embed = discord.Embed(
        title=f"{emoji} Starts in {minutes_left}m",
        description=f"{title_line}\n{details}\n{when}",
        color=color,
    )
    embed.set_footer(text=f"Lead window: {lead_minutes}m • Watch party event will be created if enabled")
    return embed

# ---- Guild resources (voice channel + scheduled event) ----
async def _ensure_voice_channel(guild: discord.Guild, name: str) -> Optional[discord.VoiceChannel]:
    # Reuse if exists
    for ch in guild.voice_channels:
        if ch.name == name:
            return ch
    # Create if missing (needs Manage Channels)
    try:
        return await guild.create_voice_channel(name=name)
    except discord.Forbidden:
        return None

async def _ensure_scheduled_event(
    guild: discord.Guild,
    channel: discord.abc.Snowflake,
    m: Match
) -> Optional[discord.GuildScheduledEvent]:
    """Create a scheduled event if not already created; return it if created."""
    if was_event_created(guild.id, m.id):
        return None

    start = m.start_time
    end = start + timedelta(hours=3)  # default event duration

    try:
        event = await guild.create_scheduled_event(
            name=f"{_tour_emoji(m.tournament)} {m.team1} vs {m.team2}",
            start_time=start,
            end_time=end,
            entity_type=discord.EntityType.voice,
            channel=channel,
            description=f"{m.tournament} • {m.stage} • {m.best_of}",
            privacy_level=discord.PrivacyLevel.guild_only,
        )
        mark_event_created(guild.id, m.id)
        return event
    except discord.Forbidden:
        return None

# ---- Alert logic ----
def _starts_within_lead(m: Match, now: datetime, lead_minutes: int) -> bool:
    if m.status == "LIVE":
        return False
    delta_min = (m.start_time - now).total_seconds() / 60.0
    return 0 < delta_min <= lead_minutes

async def start_alert_poller(bot: discord.Client):
    """Background task: checks for matches and posts one-time alerts + events."""
    await bot.wait_until_ready()

    while not bot.is_closed():
        now = datetime.now(timezone.utc)

        # Hot-reload matches module so dev edits take effect without restart
        try:
            importlib.reload(matches_module)
        except Exception as e:
            print("hot reload (alerts.py) failed:", e)

        try:
            all_matches = await matches_module.upcoming_vct_matches(limit=20)
        except Exception as e:
            print("failed to fetch matches:", e)
            all_matches = []

        # Optional debug:
        # print("poll tick:", len(all_matches), "matches loaded")

        for guild in bot.guilds:
            channel_id = get_alert_channel(guild.id)
            if not channel_id:
                continue

            chan = guild.get_channel(channel_id)
            if chan is None:
                continue

            # Per-guild settings
            lead = get_lead_minutes(guild.id, default=DEFAULT_LEAD_MINUTES)
            allow_events = is_event_enabled(guild.id, default=True)

            for m in all_matches:
                if not _starts_within_lead(m, now, lead):
                    continue
                if was_alert_sent(guild.id, m.id):
                    continue

                # Send alert
                try:
                    await chan.send(embed=_match_embed(m, lead))
                except discord.Forbidden:
                    # Missing Send Messages in this channel
                    continue
                mark_alert_sent(guild.id, m.id)

                # Create resources if enabled
                if allow_events:
                    vc_name = f"{_tour_emoji(m.tournament)} Watch • {m.team1} vs {m.team2}"
                    vc = await _ensure_voice_channel(guild, vc_name)
                    if vc:
                        event = await _ensure_scheduled_event(guild, vc, m)
                        if event is not None:
                            try:
                                await chan.send(f"📅 Watch party event created: **{event.name}** — {event.url}")
                            except Exception:
                                await chan.send(
                                    f"📅 Watch party event created: **{event.name}** (see your server’s Events tab)"
                                )

        await asyncio.sleep(POLL_INTERVAL_SECONDS)
