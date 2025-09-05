from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
import importlib

# import the module (so we can reload it), and import Match for typing
from bot.services import matches as matches_module
from bot.services.matches import Match

# --- styling per tournament ---
TOURNAMENT_ORDER = ["VCT Masters", "VCT Americas", "VCT Champions"]
TOURNAMENT_STYLE = {
    "VCT Masters":   {"emoji": "🟣", "color": discord.Color.dark_purple()},  # purple circle
    "VCT Americas":  {"emoji": "🟠", "color": discord.Color.orange()},       # orange circle
    "VCT Champions": {"emoji": "🏆", "color": discord.Color.gold()},         # trophy
}

def _tour_emoji(tournament: str) -> str:
    return TOURNAMENT_STYLE.get(tournament, {}).get("emoji", "🎮")

def _tour_color(tournament: str) -> discord.Color:
    return TOURNAMENT_STYLE.get(tournament, {}).get("color", discord.Color.blurple())

def _discord_relative(ts: datetime) -> str:
    """Discord timestamp like <t:...:R> → 'in 2 hours'"""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return f"<t:{int(ts.timestamp())}:R>"

def _status_emoji(m: Match) -> str:
    return "🔴 LIVE" if m.status == "LIVE" else "🕒 Upcoming"

def _format_line(m: Match) -> str:
    when = "LIVE now" if m.status == "LIVE" else _discord_relative(m.start_time)
    title = f"**{m.team1} vs {m.team2}**"
    details = f"{m.stage} • {m.best_of}"
    return f"{title}\n{details} — {when}"

class VCT(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="vct_matches",
        description="Show LIVE and upcoming VCT (Americas/Masters/Champions)"
    )
    async def vct_matches(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=False)

        # dev hot-reload so edits to matches.py show up without restarting the bot
        try:
            importlib.reload(matches_module)
        except Exception as e:
            print("hot reload (vct.py) failed:", e)

        matches = await matches_module.upcoming_vct_matches(limit=20)
        if not matches:
            await interaction.followup.send("No VCT matches found.")
            return

        # group by tournament
        groups = {tour: [] for tour in TOURNAMENT_ORDER}
        for m in matches:
            if m.tournament in groups:
                groups[m.tournament].append(m)
            else:
                groups.setdefault(m.tournament, []).append(m)

        sent_any = False
        ordered = TOURNAMENT_ORDER + [t for t in groups if t not in TOURNAMENT_ORDER]
        for tour in ordered:
            items = groups.get(tour, [])
            if not items:
                continue

            live = [m for m in items if m.status == "LIVE"]
            upcoming = [m for m in items if m.status != "LIVE"]

            emoji = _tour_emoji(tour)
            color = _tour_color(tour)
            embed = discord.Embed(title=f"{emoji} {tour}", color=color)

            if live:
                block = "\n\n".join(_format_line(m) for m in live)
                embed.add_field(name="🔴 LIVE", value=block, inline=False)

            if upcoming:
                now = datetime.now(timezone.utc)
                soon, later = [], []
                for m in upcoming:
                    minutes = (m.start_time - now).total_seconds() / 60
                    (soon if minutes <= 180 else later).append(m)

                if soon:
                    block = "\n\n".join(_format_line(m) for m in soon)
                    embed.add_field(name="🟡 Upcoming (≤ 3h)", value=block, inline=False)
                if later:
                    block = "\n\n".join(_format_line(m) for m in later)
                    embed.add_field(name="🟢 Upcoming (later)", value=block, inline=False)

            embed.set_footer(text="Updated just now")
            await interaction.followup.send(embed=embed)
            sent_any = True

        if not sent_any:
            await interaction.followup.send("No VCT matches to display.")

async def setup(bot: commands.Bot):
    await bot.add_cog(VCT(bot))
