import asyncio
import importlib.util
import os
import sys

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# Game folders contain hyphens, so they aren't importable packages. Each game has its own
# bot.py, so load them by file path under unique module names.
GAMES = {
    "netnaval_bot": os.path.join(os.path.dirname(__file__), "NetNaval-main"),
    "tictactoe_bot": os.path.join(os.path.dirname(__file__), "Tic-Tac-Toe"),
}
for folder in GAMES.values():
    sys.path.insert(0, folder)

UTILITIES = {
    "modmail_bot": os.path.join(os.path.dirname(__file__), "Mod-Mail"),
}


async def load_module(bot, module_name, folder, *, package=False):
    module_path = os.path.join(folder, "bot.py")
    if package:
        spec = importlib.util.spec_from_file_location(
            module_name,
            module_path,
            submodule_search_locations=[folder],
        )
    else:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load bot module from {folder}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    await module.setup(bot)


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=("!", "/", "?", ".",), case_insensitive=True, intents=intents)


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")


async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set. Add it to a .env file or environment variable.")
    async with bot:
        for modules in (GAMES, UTILITIES):
            for module_name, folder in modules.items():
                await load_module(
                    bot,
                    module_name,
                    folder,
                    package=module_name == "modmail_bot",
                )
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
