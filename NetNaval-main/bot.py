import random
from datetime import datetime, timedelta, timezone

import aiohttp
import discord
from discord.ext import commands, tasks

from rooms import Room

INACTIVITY_LIMIT = timedelta(days=2)
THREAD_AUTO_ARCHIVE = 1440  # minutes (24h), Discord's max short-lived option


def create_board():
    return [["~"]*10 for _ in range(10)]


def place_bot_ships(board, ships, count=3):
    while len(ships) < count:
        r, c = random.randint(0, 9), random.randint(0, 9)
        if board[r][c] == "~":
            board[r][c] = "S"
            ships.append((r, c))


async def render(ctx, board, hide_ships=False):
    numbers = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    letters = ["🇦","🇧","🇨","🇩","🇪","🇫","🇬","🇭","🇮","🇯"]
    display = "⬛ " + " ".join(numbers) + "\n"
    for i, row in enumerate(board):
        display += letters[i]
        for cell in row:
            if cell == "~":
                display += "🟦"
            elif cell == "S":
                display += "🟦" if hide_ships else "🚢"
            elif cell == "X":
                display += "💥"
            elif cell == "O":
                display += "⚪"
        display += "\n"
    await ctx.send(display)


async def create_game_thread(ctx, name, invite_ids=None):
    """Create a private, temporary thread for a game. Falls back to a public
    thread if the guild doesn't support private threads (requires boost level 2)."""
    try:
        thread = await ctx.channel.create_thread(
            name=name,
            type=discord.ChannelType.private_thread,
            auto_archive_duration=THREAD_AUTO_ARCHIVE,
            invitable=False,
        )
    except (discord.Forbidden, discord.HTTPException):
        thread = await ctx.channel.create_thread(
            name=name,
            type=discord.ChannelType.public_thread,
            auto_archive_duration=THREAD_AUTO_ARCHIVE,
        )
    await thread.add_user(ctx.author)
    for user_id in invite_ids or []:
        member = ctx.guild.get_member(user_id)
        if member:
            await thread.add_user(member)
    return thread


class NetNaval(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Per-thread solo game state: thread_id -> dict(board_player, board_bot,
        # board_radar, ships_player, ships_bot, last_activity)
        self.solo_games = {}
        self.cleanup_inactive_threads.start()

    def cog_unload(self):
        self.cleanup_inactive_threads.cancel()

    # ------------------------------------------------------------------
    # Inactivity cleanup
    # ------------------------------------------------------------------
    @tasks.loop(hours=1)
    async def cleanup_inactive_threads(self):
        now = datetime.now(timezone.utc)

        for room in list(Room.rooms.values()):
            if now - room.last_activity >= INACTIVITY_LIMIT:
                await self._delete_room_thread(room, "⌛ Closed due to 2 days of inactivity.")

        for thread_id, game in list(self.solo_games.items()):
            if now - game["last_activity"] >= INACTIVITY_LIMIT:
                await self._delete_solo_thread(thread_id, "⌛ Closed due to 2 days of inactivity.")

    @cleanup_inactive_threads.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    async def _delete_room_thread(self, room, reason):
        thread = self.bot.get_channel(room.thread_id) if room.thread_id else None
        Room.rooms.pop(room.pin, None)
        if thread:
            try:
                await thread.send(reason)
                await thread.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

    async def _delete_solo_thread(self, thread_id, reason):
        self.solo_games.pop(thread_id, None)
        thread = self.bot.get_channel(thread_id)
        if thread:
            try:
                await thread.send(reason)
                await thread.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    @commands.command()
    async def credits(self, ctx):
        await ctx.send(
            "🚢 **NetNaval**\n"
            "Developed by **EJ**\n"
            "Documentation: https://ej-edwards.github.io/NetNaval/\n"
            "Thanks for playing!"
        )

    @commands.command()
    async def ping(self, ctx):
        api_url = "https://netnaval.onrender.com"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=10) as resp:
                    if resp.status == 200:
                        await ctx.send("✅ API is awake and ready!")
                    else:
                        await ctx.send(f"⚠️ API responded with status {resp.status}.")
        except Exception as e:
            await ctx.send(f"❌ Could not reach the API: {e}")

    # ------------------------------------------------------------------
    # Solo mode
    # ------------------------------------------------------------------
    @commands.command(aliases=["netnaval"])
    async def start(self, ctx):
        """Start a solo game against the bot in a new private thread."""
        thread = await create_game_thread(ctx, f"NetNaval solo - {ctx.author.name}")
        board_bot = create_board()
        ships_bot = []
        place_bot_ships(board_bot, ships_bot)
        self.solo_games[thread.id] = {
            "player_id": ctx.author.id,
            "board_player": create_board(),
            "board_bot": board_bot,
            "board_radar": create_board(),
            "ships_player": [],
            "ships_bot": ships_bot,
            "last_activity": datetime.now(timezone.utc),
        }
        await ctx.send(f"🚢 Game started in your private thread: {thread.mention}")
        await thread.send("🚢 **Single-player game started!**")
        await thread.send("Place 3 ships using: `!place A1 B2 C3`")

    # ------------------------------------------------------------------
    # Multiplayer mode
    # ------------------------------------------------------------------
    @commands.command()
    async def challenge(self, ctx, opponent: discord.Member = None):
        """Create a room and private thread. Optionally challenge a specific member."""
        for room in Room.rooms.values():
            if room.host_id == ctx.author.id:
                await ctx.send(f"❌ You already have a room! PIN: {room.pin}")
                return
        if opponent and opponent.id == ctx.author.id:
            await ctx.send("❌ You can't challenge yourself.")
            return

        room = Room(ctx.author.id)
        invite_ids = [opponent.id] if opponent else []
        thread = await create_game_thread(ctx, f"NetNaval - {ctx.author.name}", invite_ids)
        room.thread_id = thread.id

        if opponent:
            room.add_player(opponent.id)
            await ctx.send(f"⚔️ {ctx.author.mention} challenged {opponent.mention} in {thread.mention}!")
            await thread.send(
                f"⚔️ {opponent.mention}, you've been challenged by {ctx.author.mention}!\n"
                "Both players place ships with `!place A1 B2 C3`."
            )
        else:
            await ctx.send(f"✅ Room created! PIN: {room.pin}\nThread: {thread.mention}")
            await thread.send(f"ℹ️ Share PIN **{room.pin}** so an opponent can `!join {room.pin}`.")

    @commands.command()
    async def create(self, ctx):
        """Alias for !challenge with no opponent (open lobby)."""
        await self.challenge(ctx)

    @commands.command()
    async def join(self, ctx, pin):
        room = Room.get_room(str(pin))
        if not room:
            await ctx.send("❌ Room not found.")
            return
        success = room.add_player(ctx.author.id)
        if not success:
            await ctx.send("❌ Room is full.")
            return
        room.touch()
        thread = self.bot.get_channel(room.thread_id) if room.thread_id else None
        if thread:
            await thread.add_user(ctx.author)
            await thread.send(f"✅ {ctx.author.mention} joined! Both players place ships with `!place A1 B2 C3`.")
        await ctx.send(f"✅ Joined room {pin}!")

    # ------------------------------------------------------------------
    # Shared gameplay commands (work for both modes, scoped by thread)
    # ------------------------------------------------------------------
    @commands.command()
    async def place(self, ctx, *positions):
        alphabet = "ABCDEFGHIJ"
        room = Room.get_room_by_thread(ctx.channel.id)

        if room:
            if ctx.author.id not in room.players:
                await ctx.send("❌ You're not part of this game.")
                return
            if len(positions) != 3:
                await ctx.send("You must place exactly 3 ships.")
                return
            board = room.boards[ctx.author.id]
            ships = room.ships[ctx.author.id]
            for pos in positions:
                try:
                    row = alphabet.index(pos[0].upper())
                    col = int(pos[1:]) - 1
                    if board[row][col] != "~":
                        raise ValueError
                except (IndexError, ValueError):
                    await ctx.send(f"❌ Invalid position: `{pos}`")
                    return
                board[row][col] = "S"
                ships.append((row, col))
            room.touch()
            await ctx.send("✅ Ships placed! **Your board:**")
            await render(ctx, board)
            return

        game = self.solo_games.get(ctx.channel.id)
        if not game:
            await ctx.send("Start a game with `!start`.")
            return
        if game["player_id"] != ctx.author.id:
            await ctx.send("❌ You're not part of this game.")
            return
        if len(positions) != 3:
            await ctx.send("You must place exactly 3 ships.")
            return
        board = game["board_player"]
        for pos in positions:
            try:
                row = alphabet.index(pos[0].upper())
                col = int(pos[1:]) - 1
                if board[row][col] != "~":
                    raise ValueError
            except (IndexError, ValueError):
                await ctx.send(f"❌ Invalid position: `{pos}`")
                return
            board[row][col] = "S"
            game["ships_player"].append((row, col))
        game["last_activity"] = datetime.now(timezone.utc)
        await ctx.send("✅ Ships placed! **Your board:**")
        await render(ctx, board)

    @commands.command()
    async def fire(self, ctx, position):
        alphabet = "ABCDEFGHIJ"
        room = Room.get_room_by_thread(ctx.channel.id)

        if room:
            if ctx.author.id != room.get_current_player():
                await ctx.send("❗ It's not your turn!")
                return
            opponent_id = next(p for p in room.players if p != ctx.author.id)
            board_opponent = room.boards[opponent_id]
            radar = room.radars[ctx.author.id]
            ships_opponent = room.ships[opponent_id]
            try:
                row = alphabet.index(position[0].upper())
                col = int(position[1:]) - 1
            except (IndexError, ValueError):
                await ctx.send("❌ Invalid position.")
                return
            if radar[row][col] in ["X", "O"]:
                await ctx.send("❗ Already fired there.")
                return
            if (row, col) in ships_opponent:
                radar[row][col] = "X"
                board_opponent[row][col] = "X"
                ships_opponent.remove((row, col))
                await ctx.send("💥 **Hit!**")
            else:
                radar[row][col] = "O"
                await ctx.send("🌊 **Miss!**")
            room.touch()
            await ctx.send("🎯 **Radar Board**")
            await render(ctx, radar, hide_ships=True)
            if not ships_opponent:
                await ctx.send(f"🏆 **{ctx.author.name} wins!**")
                await self._delete_room_thread(room, "🏆 Game over - this thread will now close.")
                return
            room.switch_turn()
            next_player = ctx.guild.get_member(room.get_current_player())
            await ctx.send(f"🔄 It's now {next_player.mention if next_player else 'the next player'}'s turn.")
            return

        game = self.solo_games.get(ctx.channel.id)
        if not game:
            await ctx.send("Start a game with `!start`.")
            return
        if game["player_id"] != ctx.author.id:
            await ctx.send("❌ You're not part of this game.")
            return
        try:
            row = alphabet.index(position[0].upper())
            col = int(position[1:]) - 1
        except (IndexError, ValueError):
            await ctx.send("❌ Invalid position. Example: `!fire B7`")
            return
        board_radar = game["board_radar"]
        if board_radar[row][col] in ["X", "O"]:
            await ctx.send("❗ Already fired there.")
            return
        ships_bot = game["ships_bot"]
        if (row, col) in ships_bot:
            board_radar[row][col] = "X"
            game["board_bot"][row][col] = "X"
            ships_bot.remove((row, col))
            await ctx.send("💥 **Hit!**")
        else:
            board_radar[row][col] = "O"
            await ctx.send("🌊 **Miss!**")
        game["last_activity"] = datetime.now(timezone.utc)
        await ctx.send("🎯 **Radar Board**")
        await render(ctx, board_radar, hide_ships=True)
        if not ships_bot:
            await ctx.send("🏆 **You sank all enemy ships — YOU WIN!**")
            await self._delete_solo_thread(ctx.channel.id, "🏆 Game over - this thread will now close.")
            return
        await self.bot_turn(ctx, game)

    async def bot_turn(self, ctx, game):
        board_player = game["board_player"]
        ships_player = game["ships_player"]
        while True:
            r, c = random.randint(0, 9), random.randint(0, 9)
            if board_player[r][c] in ["~", "S"]:
                break
        if (r, c) in ships_player:
            board_player[r][c] = "X"
            ships_player.remove((r, c))
            await ctx.send("🤖 **Bot hit your ship!**")
        else:
            board_player[r][c] = "O"
            await ctx.send("🤖 Bot missed.")
        await ctx.send("🛡️ **Your Board**")
        await render(ctx, board_player)
        if not ships_player:
            await ctx.send("💀 **All your ships were sunk — YOU LOSE.**")
            await self._delete_solo_thread(ctx.channel.id, "Game over - this thread will now close.")

    # ------------------------------------------------------------------
    # Ending games / deleting threads
    # ------------------------------------------------------------------
    @commands.command()
    async def stop(self, ctx):
        """Either player (or the solo player) can end the game and delete its thread."""
        room = Room.get_room_by_thread(ctx.channel.id)
        if room:
            if ctx.author.id not in room.players:
                await ctx.send("❌ You're not part of this game.")
                return
            await self._delete_room_thread(room, f"🛑 Game stopped by {ctx.author.name}.")
            return

        if ctx.channel.id in self.solo_games:
            game = self.solo_games[ctx.channel.id]
            if game["player_id"] != ctx.author.id:
                await ctx.send("❌ You're not part of this game.")
                return
            await self._delete_solo_thread(ctx.channel.id, f"🛑 Game stopped by {ctx.author.name}.")
            return

        await ctx.send("❌ No game to stop here.")


async def setup(bot):
    await bot.add_cog(NetNaval(bot))
