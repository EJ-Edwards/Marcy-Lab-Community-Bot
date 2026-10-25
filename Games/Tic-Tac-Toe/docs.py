class TicTacToeDocs:
    """Documentation for the Tic-Tac-Toe module for Marcy Community Bot."""

    TEXT = (
        "**Commands**\n"
        "`!tictactoe` (or `!ttt`) - Show this help.\n"
        "`!ttt solo` - Play against the bot (you are X).\n"
        "`!ttt challenge @user` - Play against another member (you are X).\n"
        "`!move <row> <col>` - Place your mark. Rows and columns are 1-3, e.g. `!move 2 2`.\n"
        "`!ttt stop` - End the game in this channel."
    )

    @staticmethod
    def text():
        return TicTacToeDocs.TEXT

    @staticmethod
    def show():
        print(TicTacToeDocs.TEXT)
