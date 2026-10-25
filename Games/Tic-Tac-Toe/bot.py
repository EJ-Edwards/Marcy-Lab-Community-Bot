import time

import discord
from discord.ext import commands

from docs import TicTacToeDocs
from multiplayer import TicTacToeMultiplayer
from solo import TicTacToeSolo

GAME_TIMEOUT = 30 * 60  # seconds of inactivity before a game in a channel is considered abandoned


class TicTacToe(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # channel_id -> {"game": Solo|Multiplayer, "last": timestamp}
        self.games = {}

    def _get(self, channel_id):
        entry = self.games.get(channel_id)
        if entry and time.monotonic() - entry["last"] > GAME_TIMEOUT:
            del self.games[channel_id]
            return None
        return entry["game"] if entry else None

    def _set(self, channel_id, game):
        self.games[channel_id] = {"game": game, "last": time.monotonic()}

    def _touch(self, channel_id):
        self.games[channel_id]["last"] = time.monotonic()

    def _end(self, channel_id):
        self.games.pop(channel_id, None)

    @commands.group(name="tictactoe", aliases=["ttt"], invoke_without_command=True)
    async def tictactoe(self, ctx):
        """Show the Tic-Tac-Toe menu."""
        embed = discord.Embed(
            title="❌⭕ Tic-Tac-Toe",
            description=TicTacToeDocs.text(),
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @tictactoe.command(name="solo")
    async def ttt_solo(self, ctx):
        if self._get(ctx.channel.id):
            await ctx.send("❌ A game is already running here. Use `!ttt stop` to end it.")
            return
        game = TicTacToeSolo(ctx.author.id)
        self._set(ctx.channel.id, game)
        await ctx.send(f"❌ {ctx.author.mention} vs 🤖 - you are X and go first. Use `!move <row> <col>` (1-3).")
        await ctx.send(game.render())

    @tictactoe.command(name="challenge")
    async def ttt_challenge(self, ctx, opponent: discord.Member):
        if opponent.bot or opponent.id == ctx.author.id:
            await ctx.send("❌ Challenge another member (not yourself or a bot).")
            return
        if self._get(ctx.channel.id):
            await ctx.send("❌ A game is already running here. Use `!ttt stop` to end it.")
            return
        game = TicTacToeMultiplayer(ctx.author.id, opponent.id)
        self._set(ctx.channel.id, game)
        await ctx.send(
            f"⚔️ {ctx.author.mention} (X) vs {opponent.mention} (O). "
            f"{ctx.author.mention} goes first. Use `!move <row> <col>` (1-3)."
        )
        await ctx.send(game.render())

    @tictactoe.command(name="stop")
    async def ttt_stop(self, ctx):
        game = self._get(ctx.channel.id)
        if not game:
            await ctx.send("❌ No Tic-Tac-Toe game here.")
            return
        players = [game.player_id] if isinstance(game, TicTacToeSolo) else game.players.values()
        if ctx.author.id not in players:
            await ctx.send("❌ You're not part of this game.")
            return
        self._end(ctx.channel.id)
        await ctx.send(f"🛑 Game stopped by {ctx.author.name}.")

    @commands.command(name="move")
    async def move(self, ctx, row: int, col: int):
        """Place your mark at <row> <col> (1-3)."""
        game = self._get(ctx.channel.id)
        if not game:
            await ctx.send("No Tic-Tac-Toe game here. Start one with `!ttt solo` or `!ttt challenge @user`.")
            return
        solo = isinstance(game, TicTacToeSolo)

        if solo:
            if ctx.author.id != game.player_id:
                await ctx.send("❌ You're not part of this game.")
                return
            mark = "X"
        else:
            if ctx.author.id not in game.players.values():
                await ctx.send("❌ You're not part of this game.")
                return
            if ctx.author.id != game.current_player_id():
                await ctx.send("❗ It's not your turn!")
                return
            mark = game.turn

        if not game.place_mark(row - 1, col - 1, mark):
            await ctx.send("❌ Invalid move: use row and column 1-3 on an empty cell.")
            return
        self._touch(ctx.channel.id)

        if game.check_winner(mark):
            await ctx.send(game.render())
            await ctx.send(f"🏆 {ctx.author.mention} wins!")
            self._end(ctx.channel.id)
            return
        if game.is_full():
            await ctx.send(game.render())
            await ctx.send("🤝 It's a draw!")
            self._end(ctx.channel.id)
            return

        if solo:
            game.bot_move()
            await ctx.send(game.render())
            if game.check_winner("O"):
                await ctx.send("🤖 The bot wins!")
                self._end(ctx.channel.id)
            elif game.is_full():
                await ctx.send("🤝 It's a draw!")
                self._end(ctx.channel.id)
            return

        game.switch_turn()
        nxt = ctx.guild.get_member(game.current_player_id())
        await ctx.send(game.render())
        await ctx.send(f"🔄 {nxt.mention if nxt else 'Next player'}, your turn ({game.turn}).")

    async def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    async def cog_command_error(self, ctx, error):
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send("❌ Invalid input. Example: `!move 2 2`. Use `!ttt` for help.")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("❌ Use this command in a server.")
        else:
            raise error


async def setup(bot):
    await bot.add_cog(TicTacToe(bot))
