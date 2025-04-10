class Broadcaster:
    def __init__(self, player_manager, board):
        self.player_manager = player_manager
        self.board = board

    def broadcast(self, message, sender_socket=None, exclude_sender=False):
        encoded = message.encode('utf-8')
        for sock in list(self.player_manager.clients.keys()):
            if exclude_sender and sock == sender_socket:
                continue
            try:
                sock.sendall(encoded)
            except:
                pass 

    def broadcast_board(self):
        board_repr = repr(self.board.get_board())
        self.broadcast(f"UPDATE_BOARD|{board_repr}\n")

    def broadcast_players(self):
        players = repr(self.player_manager.get_players())
        self.broadcast(f"UPDATE_PLAYERS|{players}\n")

    def broadcast_scores(self):
        board_data = self.board.get_board()
        score_map = {}
        for row in board_data:
            for pid in row:
                if pid != 0:
                    score_map[pid] = score_map.get(pid, 0) + 1
        self.broadcast(f"UPDATE_SCORES|{repr(score_map)}\n")

    def broadcast_lock(self, r, c, player_id):
        self.broadcast(f"SQUARE_LOCKED|{r}|{c}|{player_id}\n")

    def broadcast_unlock(self, r, c):
        self.broadcast(f"SQUARE_UNLOCKED|{r}|{c}\n")
