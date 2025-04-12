import socket
import threading
import sys
import time
from .board import GameBoard
from .broadcaster import Broadcaster
from .player_manager import PlayerManager

class GameServer:
    """The GameServer class is responsible for
    starting and stopping the game server."""

    def __init__(self, host='0.0.0.0', port=65433, grid_size=8, max_players=4):
        """
        Initialize the GameServer instance with given parameters.
        """
        self.host = host
        self.port = port
        self.grid_size = grid_size
        self.max_players = max_players

        # Create the server socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Make the socket reusable
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Create the player manager and board and reference to the game server
        self.player_manager = PlayerManager(max_players)
        self.player_manager.set_game_server(self)  
        self.board = GameBoard(grid_size)
        # Create the broadcaster
        self.broadcaster = Broadcaster(self.player_manager, self.board)
        self.game_active = True
        self.timer_duration = 120  # Timer duration in seconds (2 minutes)
        self.timer_start_time = None  # To track when the timer starts
        self.timer_started = False  # To track if timer has been started

    def start(self):
        """
        Start the game server and listen for incoming connections.
        """
        try:
            # Bind the socket to the host and port
            self.server_socket.bind((self.host, self.port))

            # Listen for incoming connections
            self.server_socket.listen()
            print(f"Deny & Conquer Server listening on {self.host}:{self.port}")
            print(f"Grid Size: {self.grid_size}x{self.grid_size}, Max Players: {self.max_players}")

            # Start a thread to broadcast the timer
            timer_thread = threading.Thread(target=self.broadcast_timer, daemon=True)
            timer_thread.start()

            # Start accepting connections
            while self.game_active:
                try:
                    # Accept a connection
                    client_socket, addr = self.server_socket.accept()
                    print(f"Accepted connection from {addr}")

                    # Start a new thread to handle the client
                    client_thread = threading.Thread(
                        target=self.player_manager.handle_client,
                        args=(client_socket, addr, self.board, self.broadcaster, self.check_game_over),
                        daemon=True,
                    )
                    client_thread.start()

                except KeyboardInterrupt:
                    print("\nCtrl+C detected. Shutting down server...")
                    self.game_active = False
                    break
                except Exception as e:
                    print(f"Error accepting connection: {e}")
        finally:
            # Shut down the server when we're done
            self.shutdown()

    def broadcast_timer(self):
        """
        Broadcast the remaining time to all clients at regular intervals.
        """
        while self.game_active:
            if self.timer_start_time is not None:
                elapsed_time = time.time() - self.timer_start_time
                remaining_time = max(0, self.timer_duration - int(elapsed_time))
                self.broadcaster.broadcast(f"TIMER_UPDATE|{remaining_time}\n")

                # End the game if the timer reaches 0
                if remaining_time == 0:
                    self.check_game_over()
                    break

            time.sleep(1)  # Broadcast every second

    def check_game_over(self):
        """
        Check if the game is over and broadcast the result if so.
        Game ends when either:
        1. The board is full
        2. The timer has reached zero
        """
        if self.board.is_full() or (self.timer_started and time.time() - self.timer_start_time >= self.timer_duration):
            self.game_active = False
            result_msg = self.board.calculate_winner(self.player_manager)
            print(result_msg)
            self.broadcaster.broadcast(f"GAME_OVER|{result_msg}\n")
            # Schedule server shutdown after 30 seconds
            print("Server will shut down in 30 seconds...")
            threading.Timer(20, self.shutdown).start()

    def shutdown(self):
        """
        Shutdown the server and close all connections.
        """
        print("Shutting down server...")
        self.game_active = False
        self.broadcaster.broadcast("INFO|Server is shutting down.\n")
        self.player_manager.disconnect_all()
        self.server_socket.close()
        print("Server shut down.")
        sys.exit(0)
