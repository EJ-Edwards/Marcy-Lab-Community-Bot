import random
from datetime import datetime, timezone

class Room:
    rooms = {}
    def __init__(self, host_id):
        self.host_id = host_id
        self.players = [host_id]
        self.boards = {host_id: [["~"]*10 for _ in range(10)]}
        self.ships = {host_id: []}
        self.radars = {host_id: [["~"]*10 for _ in range(10)]}
        self.turn_index = 0
        self.pin = self.generate_pin()
        self.thread_id = None
        self.last_activity = datetime.now(timezone.utc)
        Room.rooms[self.pin] = self

    def touch(self):
        self.last_activity = datetime.now(timezone.utc)

    @staticmethod
    def generate_pin():
        while True:
            pin = str(random.randint(1000, 9999))
            if pin not in Room.rooms:
                return pin

    @classmethod
    def get_room(cls, pin):
        return cls.rooms.get(str(pin))

    @classmethod
    def get_room_by_thread(cls, thread_id):
        return next((r for r in cls.rooms.values() if r.thread_id == thread_id), None)

    def add_player(self, player_id):
        if len(self.players) >= 2:
            return False
        if player_id not in self.players:
            self.players.append(player_id)
            self.boards[player_id] = [["~"]*10 for _ in range(10)]
            self.ships[player_id] = []
            self.radars[player_id] = [["~"]*10 for _ in range(10)]
        return True

    def remove_player(self, player_id):
        if player_id in self.players:
            self.players.remove(player_id)
            self.boards.pop(player_id, None)
            self.ships.pop(player_id, None)
            self.radars.pop(player_id, None)
            if self.turn_index >= len(self.players):
                self.turn_index = 0
        if not self.players:
            del Room.rooms[self.pin]

    def get_current_player(self):
        if not self.players:
            return None
        return self.players[self.turn_index]

    def switch_turn(self):
        if len(self.players) > 1:
            self.turn_index = (self.turn_index + 1) % len(self.players)
