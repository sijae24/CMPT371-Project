import threading
from collections import defaultdict

class GameBoard:
    """
    The GameBoard class is a 2D array of player IDs, where 0 represents an empty square.
    The board is also responsible for keeping track of which squares are locked by which players.
    """
    def __init__(self, grid_size):
        """
        Initialize the game board with given grid size.
        """
        self.grid_size = grid_size
        self.board = [[0] * grid_size for _ in range(grid_size)]
        self.locks = {}
        self.lock = threading.Lock()
        self.claimed_squares = 0  # New counter for claimed squares

    def try_lock(self, r, c, player_id):
        """
        Try to lock the given square for the given player
        """
        with self.lock:
            # Check if the square is available
            if (0 <= r < self.grid_size and 0 <= c < self.grid_size
                and self.board[r][c] == 0 and (r, c) not in self.locks):
                # Lock the square
                self.locks[(r, c)] = player_id
                return True
            return False

    def claim(self, r, c, player_id):
        """
        Claim the given square for the given player if it is locked by them
        """
        with self.lock:
            # Check if the square is locked by the player
            if self.locks.get((r, c)) == player_id:
                self.board[r][c] = player_id
                # Release the square
                del self.locks[(r, c)]
                self.claimed_squares += 1  # Increment the counter
                return True
            return False

    def release_lock(self, r, c, player_id):
        """
        Release the given square if it is locked by the given player
        """
        with self.lock:
            # Check if the square is locked by the player
            if self.locks.get((r, c)) == player_id:
                # Release the square
                del self.locks[(r, c)]
                return True
            return False

    def release_all_locks(self, player_id):
        """
        Release all squares locked by the given player
        """
        with self.lock:
            # Find all locked squares by the player
            to_release = [(r, c) for (r, c), pid in self.locks.items() if pid == player_id]
            for key in to_release:
                # Release the locked square
                del self.locks[key]

    def is_full(self):
        """
        Check if all squares are claimed
        """
        with self.lock:
            return self.claimed_squares == self.grid_size * self.grid_size

    def calculate_winner(self, player_manager):
        """
        Calculate the winner of the game
        """
        with self.lock:
            # Calculate score for each player
            score_map = defaultdict(int)
            # Count the number of squares claimed by each player
            for r in range(self.grid_size):
                for c in range(self.grid_size):
                    # Get the player ID of the square
                    pid = self.board[r][c]
                    if pid:
                        score_map[pid] += 1 # Increment the score

            if not score_map:
                return "Game Over! No squares claimed."

            # Find the player(s) with the highest score
            max_score = max(score_map.values())
            winners = [pid for pid, score in score_map.items() if score == max_score]

            # Get the names of the winner(s)
            players = player_manager.get_players()
            winner_names = [players[pid]['name'] for pid in winners]

            if len(winner_names) == 1:
                return f"Game Over! {winner_names[0]} wins with {max_score} squares!"
            return f"Game Over! It's a tie between {', '.join(winner_names)} with {max_score} squares!"

    def get_board(self):
        """
        Get a copy of the game board
        """
        with self.lock:
            return [row[:] for row in self.board]

    def get_locks(self):
        """
        Get a copy of the locks
        """
        with self.lock:
            return dict(self.locks)

