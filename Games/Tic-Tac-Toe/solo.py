import random

LINES = (
    [[(r, c) for c in range(3)] for r in range(3)]
    + [[(r, c) for r in range(3)] for c in range(3)]
    + [[(i, i) for i in range(3)], [(i, 2 - i) for i in range(3)]]
)


class TicTacToeSolo:
    """Player (X) vs the bot (O)."""

    def __init__(self, player_id):
        self.player_id = player_id
        self.board = [[" " for _ in range(3)] for _ in range(3)]

    def place_mark(self, row, col, mark):
        if 0 <= row < 3 and 0 <= col < 3 and self.board[row][col] == " ":
            self.board[row][col] = mark
            return True
        return False

    def is_full(self):
        return all(cell != " " for row in self.board for cell in row)

    def check_winner(self, mark):
        return any(all(self.board[r][c] == mark for r, c in line) for line in LINES)

    def reset_board(self):
        self.board = [[" " for _ in range(3)] for _ in range(3)]

    def _winning_cell(self, mark):
        for line in LINES:
            cells = [self.board[r][c] for r, c in line]
            if cells.count(mark) == 2 and cells.count(" ") == 1:
                return line[cells.index(" ")]
        return None

    def bot_move(self):
        """Bot plays O: win if possible, otherwise block, then center, then random."""
        empty = [(r, c) for r in range(3) for c in range(3) if self.board[r][c] == " "]
        if not empty:
            return None
        move = self._winning_cell("O") or self._winning_cell("X")
        if move is None:
            move = (1, 1) if (1, 1) in empty else random.choice(empty)
        self.place_mark(move[0], move[1], "O")
        return move

    def render(self):
        rows = [" | ".join(row) for row in self.board]
        return "```\n" + "\n---------\n".join(rows) + "\n```"
