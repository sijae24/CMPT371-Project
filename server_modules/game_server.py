import socket
import threading
import sys
from server_modules.player_manager import PlayerManager
from server_modules.board import GameBoard
from server_modules.broadcaster import Broadcaster

class GameServer:
    def __init__(self, host='0.0.0.0', port=65433, grid_size=8, max_players=4):
        self.host = host
        self.port = port
        self.grid_size = grid_size
        self.max_players = max_players

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.player_manager = PlayerManager(max_players)
        self.board = GameBoard(grid_size)
        self.broadcaster = Broadcaster(self.player_manager, self.board)
        self.game_active = True

    def start(self):
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen()
            print(f"Deny & Conquer Server listening on {self.host}:{self.port}")
            print(f"Grid Size: {self.grid_size}x{self.grid_size}, Max Players: {self.max_players}")

            while self.game_active:
                try:
                    client_socket, addr = self.server_socket.accept()
                    print(f"Accepted connection from {addr}")
                    client_thread = threading.Thread(
                        target=self.player_manager.handle_client,
                        args=(client_socket, addr, self.board, self.broadcaster, self.check_game_over),
                        daemon=True
                    )
                    client_thread.start()
                except KeyboardInterrupt:
                    print("\nCtrl+C detected. Shutting down server...")
                    self.game_active = False
                    break
                except Exception as e:
                    print(f"Error accepting connection: {e}")
        finally:
            self.shutdown()

    def check_game_over(self):
        if self.board.is_full():
            self.game_active = False
            result_msg = self.board.calculate_winner(self.player_manager)
            print(result_msg)
            self.broadcaster.broadcast(f"GAME_OVER|{result_msg}\n")

    def shutdown(self):
        print("Shutting down server...")
        self.broadcaster.broadcast("INFO|Server is shutting down.\n")
        self.player_manager.disconnect_all()
        self.server_socket.close()
        print("Server shut down.")
        sys.exit(0)