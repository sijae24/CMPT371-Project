import socket
import threading
import sys
from server_modules.player_manager import PlayerManager
from server_modules.board import GameBoard
from server_modules.broadcaster import Broadcaster

class GameServer:
    """ The GameServer class is responsible for 
        starting and stopping the game server. """
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

        # Create the player manager and board
        self.player_manager = PlayerManager(max_players)
        self.board = GameBoard(grid_size)
        # Create the broadcaster
        self.broadcaster = Broadcaster(self.player_manager, self.board)
        self.game_active = True

    def start(self):
        """
        Start the game server and listen for incoming connections.
        """
        try:
            #  Bind the socket to the host and port
            self.server_socket.bind((self.host, self.port))

            # Listen for incoming connections
            self.server_socket.listen()
            print(f"Deny & Conquer Server listening on {self.host}:{self.port}")
            print(f"Grid Size: {self.grid_size}x{self.grid_size}, Max Players: {self.max_players}")

            # Start accepting connections
            while self.game_active:
                try:
                    # Accept a connection
                    client_socket, addr = self.server_socket.accept()
                    print(f"Accepted connection from {addr}")

                    # Start a new thread to handle the client by passing the client socket and address
                    client_thread = threading.Thread(
                        target=self.player_manager.handle_client,
                        # The arguments are the new client socket and its address
                        args=(client_socket, addr,
                              # the board to play on
                              self.board,
                              # the broadcaster to send messages with
                              self.broadcaster,
                              # the function to call when the game is over
                              self.check_game_over),
                        # Set daemon to True so that the thread exits when the main thread does
                        daemon=True
                    )

                    # Start the new thread
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

    def check_game_over(self):
        """
        Check if the game is over and broadcast the result if so.
        """
        if self.board.is_full():
            self.game_active = False
            result_msg = self.board.calculate_winner(self.player_manager)
            print(result_msg)
            self.broadcaster.broadcast(f"GAME_OVER|{result_msg}\n")

    def shutdown(self):
        """
        Shutdown the server and close all connections.
        """
        print("Shutting down server...")
        self.broadcaster.broadcast("INFO|Server is shutting down.\n")
        self.player_manager.disconnect_all()
        self.server_socket.close()
        print("Server shut down.")
        sys.exit(0)
