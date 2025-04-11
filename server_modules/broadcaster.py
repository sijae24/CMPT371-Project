class Broadcaster:
    """ The Broadcaster class is responsible 
        for broadcasting messages to all connected clients. """
    def __init__(self, player_manager, board):
        """ Initialize the broadcaster with a player manager and board. """
        self.player_manager = player_manager
        self.board = board

    def broadcast(self, message, sender_socket=None, exclude_sender=False):
        """ Broadcast a message to all connected clients. """
        encoded = message.encode('utf-8')
        # Send the message to all connected clients
        for sock in list(self.player_manager.clients.keys()):
            # Exclude the sender 
            if exclude_sender and sock == sender_socket:
                continue
            try:
                sock.sendall(encoded)
            except:
                pass 

    def broadcast_board(self):
        """ Broadcast the current state of the board. """
        board_repr = repr(self.board.get_board())
        self.broadcast(f"UPDATE_BOARD|{board_repr}\n")

    def broadcast_players(self):
        """ Broadcast the current list of players. """
        players = repr(self.player_manager.get_players())
        self.broadcast(f"UPDATE_PLAYERS|{players}\n")

    def broadcast_scores(self):
        """ Broadcast the current scores. """
        board_data = self.board.get_board()
        # Count the number of squares claimed by each player
        score_map = {}
        for row in board_data:
            for pid in row:
                if pid != 0:
                    score_map[pid] = score_map.get(pid, 0) + 1 # Increment the score 
        self.broadcast(f"UPDATE_SCORES|{repr(score_map)}\n")

    def broadcast_lock(self, r, c, player_id):
        """ Broadcast that a square has been locked. """
        self.broadcast(f"SQUARE_LOCKED|{r}|{c}|{player_id}\n")

    def broadcast_unlock(self, r, c):
        """Broadcast that a square has been unlocked."""
        self.broadcast(f"SQUARE_UNLOCKED|{r}|{c}\n")

