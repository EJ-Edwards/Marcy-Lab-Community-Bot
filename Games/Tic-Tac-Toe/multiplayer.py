LINES = (
    [[(r, c) for c in range(3)] for r in range(3)]
    + [[(r, c) for r in range(3)] for c in range(3)]
    + [[(i, i) for i in range(3)], [(i, 2 - i) for i in range(3)]]
)


class TicTacToeMultiplayer:
    """Two players: x_id plays X and goes first, o_id plays O."""

    def __init__(self, x_id, o_id):
        self.players = {"X": x_id, "O": o_id}
        self.turn = "X"
        self.board = [[" " for _ in range(3)] for _ in range(3)]

    def current_player_id(self):
        return self.players[self.turn]

    def switch_turn(self):
        self.turn = "O" if self.turn == "X" else "X"

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
        self.turn = "X"

    def render(self):
        rows = [" | ".join(row) for row in self.board]
        return "```\n" + "\n---------\n".join(rows) + "\n```"
