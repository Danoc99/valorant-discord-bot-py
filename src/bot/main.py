import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from bot.services.alerts import start_alert_poller
import asyncio


# Load variables from .env into environment
load_dotenv()

# Read token + guild id (strip = remove stray spaces/newlines)
TOKEN = (os.getenv("DISCORD_TOKEN") or "").strip()
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing. Check .env")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

#Intents to tell Disc what events you want.
intents = discord.Intents.default()

#commands.Bot gives slash-command tree (bot.tree)
bot = commands.Bot(command_prefix="!", intents=intents)

#on_ready Fires once bot successfully connects and is ready to receive events
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    #Fast dev sync: push slash commands to a single guild (the server)
    if GUILD_ID:
        guild_obj = discord.Object(id=GUILD_ID)

        #If later defining global commands, copy to guild to see them instantly
        try:
            bot.tree.copy_global_to(guild=guild_obj)
        except Exception:
            pass #No global commands yet

        synced = await bot.tree.sync(guild=guild_obj)
        print(f"Synced {len(synced)} slash command(s) to guild {GUILD_ID}")
    else:
        #Fallback
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} global slash command(s)")
    # Start the background alert poller once
    if not hasattr(bot, "_alert_task"):
        bot._alert_task = asyncio.create_task(start_alert_poller(bot))
        print("🚨 Alert poller started")


async def main():
    # Load extensions
    await bot.load_extension("bot.cogs.basic")
    await bot.load_extension("bot.cogs.admin")
    await bot.load_extension("bot.cogs.vct")
    await bot.load_extension("bot.cogs.settings")
    # Start the connection using token
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
