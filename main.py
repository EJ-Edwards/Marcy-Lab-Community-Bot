import asyncio
import os
import sys

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# bot.py/rooms.py live in this nested folder, not a proper Python package (hyphens in names)
GAME_DIR = os.path.join(os.path.dirname(__file__), "NetNaval-main")
sys.path.insert(0, GAME_DIR)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", case_insensitive=True, intents=intents)


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")


async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set. Add it to a .env file or environment variable.")
    async with bot:
        await bot.load_extension("bot")
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
