import threading
from collections import defaultdict

class GameBoard:
    def __init__(self, grid_size):
        self.grid_size = grid_size
        self.board = [[0] * grid_size for _ in range(grid_size)]
        self.locks = {}  
        self.lock = threading.Lock()

    def try_lock(self, r, c, player_id):
        with self.lock:
            if (0 <= r < self.grid_size and 0 <= c < self.grid_size
                and self.board[r][c] == 0 and (r, c) not in self.locks):
                self.locks[(r, c)] = player_id
                return True
            return False

    def claim(self, r, c, player_id):
        with self.lock:
            if self.locks.get((r, c)) == player_id:
                self.board[r][c] = player_id
                del self.locks[(r, c)]
                return True
            return False

    def release_lock(self, r, c, player_id):
        with self.lock:
            if self.locks.get((r, c)) == player_id:
                del self.locks[(r, c)]
                return True
            return False

    def release_all_locks(self, player_id):
        with self.lock:
            to_release = [(r, c) for (r, c), pid in self.locks.items() if pid == player_id]
            for key in to_release:
                del self.locks[key]

    def is_full(self):
        with self.lock:
            return all(self.board[r][c] != 0 for r in range(self.grid_size) for c in range(self.grid_size))

    def calculate_winner(self, player_manager):
        with self.lock:
            score_map = defaultdict(int)
            for r in range(self.grid_size):
                for c in range(self.grid_size):
                    pid = self.board[r][c]
                    if pid:
                        score_map[pid] += 1

            if not score_map:
                return "Game Over! No squares claimed."

            max_score = max(score_map.values())
            winners = [pid for pid, score in score_map.items() if score == max_score]

            players = player_manager.get_players()
            winner_names = [players[pid]['name'] for pid in winners]

            if len(winner_names) == 1:
                return f"Game Over! {winner_names[0]} wins with {max_score} squares!"
            return f"Game Over! It's a tie between {', '.join(winner_names)} with {max_score} squares!"

    def get_board(self):
        with self.lock:
            return [row[:] for row in self.board]

    def get_locks(self):
        with self.lock:
            return dict(self.locks)
