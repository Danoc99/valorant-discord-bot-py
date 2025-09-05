import discord
from discord import app_commands
from discord.ext import commands
from bot.services.storage import (
    get_lead_minutes, set_lead_minutes,
    is_event_enabled, set_event_enabled,
)

MANAGE_PERMS = app_commands.checks.has_permissions(manage_guild=True)

class VCTSettings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="vct_settings_show", description="Show current VCT alert settings for this server")
    async def show(self, interaction: discord.Interaction):
        lead = get_lead_minutes(interaction.guild_id)
        events = is_event_enabled(interaction.guild_id)
        await interaction.response.send_message(
            f"**VCT Settings**\n• Lead minutes: **{lead}**\n• Event creation: **{'ON' if events else 'OFF'}**",
            ephemeral=True
        )

    @MANAGE_PERMS
    @app_commands.command(name="vct_settings_lead", description="Set alert lead time (minutes, 5–180)")
    @app_commands.describe(minutes="How many minutes before start to alert (5–180)")
    async def set_lead(self, interaction: discord.Interaction, minutes: int):
        set_lead_minutes(interaction.guild_id, minutes)
        new_val = get_lead_minutes(interaction.guild_id)
        await interaction.response.send_message(
            f"✅ Lead time set to **{new_val} minutes**.",
            ephemeral=True
        )

    @MANAGE_PERMS
    @app_commands.command(name="vct_settings_events", description="Enable or disable creating watch-party events")
    @app_commands.describe(enabled="true = create events, false = do not create events")
    async def set_events(self, interaction: discord.Interaction, enabled: bool):
        set_event_enabled(interaction.guild_id, enabled)
        await interaction.response.send_message(
            f"✅ Event creation **{'ENABLED' if enabled else 'DISABLED'}**.",
            ephemeral=True
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(VCTSettings(bot))
