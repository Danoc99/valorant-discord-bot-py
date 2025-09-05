import discord
from discord import app_commands
from discord.ext import commands

class Basic(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot  # keep a reference if we need it later

    @app_commands.command(name="ping", description="Replies with pong!")
    async def ping(self, interaction: discord.Interaction):
        # interaction = the context of this slash command invocation
        await interaction.response.send_message("pong!")

async def setup(bot: commands.Bot):
    # This function is called by bot.load_extension(...)
    await bot.add_cog(Basic(bot))
