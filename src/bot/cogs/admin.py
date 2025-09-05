import discord
from discord import app_commands
from discord.ext import commands
from bot.services.storage import set_alert_channel, get_alert_channel

class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="set_alert_channel",
        description="Use in the channel where VCT alerts should be posted."
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def set_alert_channel_cmd(self, interaction: discord.Interaction):
        # Save this channel as the alert destination for this guild
        set_alert_channel(interaction.guild_id, interaction.channel_id)
        await interaction.response.send_message(
            f"✅ Alerts will post in <#{interaction.channel_id}>.",
            ephemeral=True
        )

    # Friendly error if the user lacks permission
    @set_alert_channel_cmd.error
    async def set_alert_channel_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message(
                "You need **Manage Channels** to run this command.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("⚠️ Something went wrong.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
