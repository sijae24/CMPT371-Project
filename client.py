import socket
import threading
import pygame
import queue
import ast
import time
import sys
from client_modules.constants import *
from client_modules import GridComponent, LoginComponent


class GameClient:
    """Represents the game client responsible for managing the game state, UI, and network connections."""
    def __init__(self):
        """
        Initialize the GameClient instance. Set up the pygame display,
        initialize the required fonts, and set up the network and game state.
        """
        pygame.init()
        pygame.font.init()

        # Load window icon
        try:
            import os

            icon_path = os.path.join(os.path.dirname(__file__), "assets", "draw.png")
            window_icon = pygame.image.load(icon_path)
            pygame.display.set_icon(window_icon)
        except Exception as e:
            print(f"Could not load window icon: {e}")

        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Deny & Conquer Client (Pygame)")
        self.clock = pygame.time.Clock()

        try:
            self.font_ui = pygame.font.SysFont("Calibri", 16)
            self.font_ui_small = pygame.font.SysFont("Calibri", 14)
            self.font_title = pygame.font.SysFont("Calibri", 24, bold=True)
            self.font_status = pygame.font.SysFont("Calibri", 18)
            self.font_lock = pygame.font.SysFont("Arial", 10)
        except pygame.error:
            self.font_ui = pygame.font.SysFont("Arial", 16)
            self.font_ui_small = pygame.font.SysFont("Arial", 14)
            self.font_title = pygame.font.SysFont("Arial", 24, bold=True)
            self.font_status = pygame.font.SysFont("Arial", 18)
            self.font_lock = pygame.font.SysFont("Arial", 10)

        # --- Network State ---
        self.sock = None
        self.connected = False
        self.receive_thread = None
        self.message_queue = queue.Queue()

        # --- Game State ---
        self.player_name = ""
        self.server_ip = "127.0.0.1"
        self.server_port = "65433"
        self.my_player_id = -1
        self.my_color_tuple = (0, 0, 0)
        self.my_color_str = 'black'
        self.grid_size = 8
        self.board = []
        self.players = {}
        self.locked_squares = {}
        self.game_over = False
        self.game_over_message = ""
        self.status_text = "Enter details and connect."
        self.status_color = COLOR_STATUS_INFO
        self.remaining_time = 120

        # --- Scribbling State ---
        self.is_scribbling = False
        self.scribble_square = None
        self.pending_lock_request = None
        self.other_players_scribbles = {} 
        self.current_scene = "login"

        # --- Components ---
        self.login = LoginComponent(self)
        self.grid = GridComponent(self)

        # Start processing network messages
        self.start_queue_processing()

    def hex_to_rgb(self, hex_color):
        """ Converts a given hex color to an RGB tuple."""

        if not hasattr(self, '_color_cache'):
            self._color_cache = {}
        if hex_color not in self._color_cache:
            hex_color = hex_color.lstrip('#')
            try:
                self._color_cache[hex_color] = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
            except ValueError:
                print(f"Warning: Invalid color hex {hex_color}, using black.")
                self._color_cache[hex_color] = (0, 0, 0)
        return self._color_cache[hex_color]

    # === Network Methods for Connecting with Server ===
    def connect_to_game(self):
        """Connect to the game server using the provided IP and port."""
        if not self.player_name:
            self.set_status("Player Name cannot be empty.", COLOR_STATUS_ERROR)
            return
        if not self.server_ip:
            self.set_status("Server IP cannot be empty.", COLOR_STATUS_ERROR)
            return
        try:
            port_num = int(self.server_port)
            if not (1024 < port_num < 65536):
                raise ValueError("Port out of range")
        except ValueError:
            self.set_status("Invalid Port number (1025-65535).", COLOR_STATUS_ERROR)
            return

        try:
            self.set_status(f"Connecting to {self.server_ip}:{self.server_port}...", COLOR_STATUS_INFO)
            # Create a socket and connect to the server
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.server_ip, port_num))
            self.connected = True
            self.game_over = False
            self.game_over_message = ""

            # Send connection message to server
            connect_msg = f"CONNECT|{self.player_name}\n"
            self.sock.sendall(connect_msg.encode('utf-8'))

            self.receive_thread = threading.Thread(target=self.receive_messages, daemon=True)
            self.receive_thread.start()
            self.log_message(f"Connection attempt initiated...")

        except ConnectionRefusedError:
            self.set_status(f"Connection refused. Server offline?", COLOR_STATUS_ERROR)
            self.cleanup_connection()
        except socket.timeout:
            self.set_status(f"Connection timed out.", COLOR_STATUS_ERROR)
            self.cleanup_connection()
        except socket.gaierror:
            self.set_status(f"Could not resolve hostname.", COLOR_STATUS_ERROR)
            self.cleanup_connection()
        except Exception as e:
            self.set_status(f"Connection failed: {e}", COLOR_STATUS_ERROR)
            self.cleanup_connection()

    def receive_messages(self):
        """ Receive messages from the server and process them."""
        buffer = ""
        while self.connected and self.sock:
            try:
                data = self.sock.recv(BUFFER_SIZE)
                if not data:
                    self.message_queue.put(("DISCONNECT", "Server closed connection."))
                    break
                buffer += data.decode('utf-8')
                while '\n' in buffer:
                    message, buffer = buffer.split('\n', 1)
                    if message:
                        self.message_queue.put(("MESSAGE", message.strip()))
            except ConnectionResetError:
                self.message_queue.put(("DISCONNECT", "Connection reset."))
                break
            except socket.timeout:
                self.log_message("Network receive timeout (expected during inactivity).")
                continue
            except OSError as e:
                if self.connected:
                    self.message_queue.put(("DISCONNECT", f"Network error: {e}"))
                break
            except Exception as e:
                if self.connected:
                    self.message_queue.put(("DISCONNECT", f"Receive error: {e}"))
                break
        self.connected = False
        print("Receive thread finished.")

    def process_queue(self):
        """Process messages in the queue."""
        try:
            while not self.message_queue.empty():
                msg_type, data = self.message_queue.get_nowait()
                if msg_type == "MESSAGE":
                    self.handle_server_message(data)
                elif msg_type == "DISCONNECT":
                    self.handle_disconnection(data)
        except queue.Empty:
            pass

    def handle_server_message(self, message):
        """Handle messages received from the server."""

        # Only print non-scribble messages to reduce terminal spam
        if not message.startswith("PLAYER_SCRIBBLE"):
            print(f"Received: {message}")

        try:
            # Split the message into command and payload
            parts = message.split('|', 1)
            command = parts[0]
            payload = parts[1] if len(parts) > 1 else ""

            # Welcome message
            if command == "WELCOME":
                p_parts = payload.split('|')
                self.my_player_id = int(p_parts[0])
                self.my_color_str = p_parts[1]
                self.my_color_tuple = self.hex_to_rgb(self.my_color_str)
                self.grid_size = int(p_parts[2])
                pygame.display.set_caption(f"Deny & Conquer - {self.player_name} (ID: {self.my_player_id})")
                self.log_message(f"Connected! Your color: {self.my_color_str}")
                self.current_scene = "game"
                self.board = [[0] * self.grid_size for _ in range(self.grid_size)]
                self.grid.calculate_square_size()
                self.set_status("Game started! Click white squares.", COLOR_STATUS_INFO)


            # Update board where the player has scribbled
            elif command == "UPDATE_BOARD":
                new_board = ast.literal_eval(payload)
                # Check for newly claimed squares and clear their scribbles
                if self.board:
                    for r in range(self.grid_size):
                        for c in range(self.grid_size):
                            # If a square was empty and is now claimed
                            if self.board[r][c] == 0 and new_board[r][c] != 0:
                                # Clear any scribbles for this square
                                if (r, c) in self.other_players_scribbles:
                                    del self.other_players_scribbles[(r, c)]
                                # If this was our scribble square, reset it
                                if self.scribble_square == (r, c):
                                    self.is_scribbling = False
                                    self.scribble_square = None
                                    self.grid.reset_scribble_state()

                self.board = new_board

            # Update player list
            elif command == "UPDATE_PLAYERS":
                self.players = ast.literal_eval(payload)


            # Lock requests and responses
            elif command == "LOCK_GRANTED":
                r, c = map(int, payload.split('|'))
                if self.pending_lock_request == (r, c):
                    print(f"Lock granted for ({r},{c})")
                    self.is_scribbling = True
                    self.scribble_square = (r, c)
                    self.locked_squares[(r, c)] = self.my_player_id
                    self.set_status(f"Scribbling in ({r},{c})...", COLOR_STATUS_INFO)
                else:
                    print(f"WARN: LOCK_GRANTED for unexpected square ({r},{c})")
                self.pending_lock_request = None

            elif command == "LOCK_DENIED":
                r, c = map(int, payload.split('|'))
                if self.pending_lock_request == (r, c):
                    self.set_status(f"Lock denied for ({r},{c}). Busy?", COLOR_STATUS_ERROR)
                    self.log_message(f"Lock denied for square ({r},{c}).")
                    self.pending_lock_request = None

            elif command == "SQUARE_LOCKED":
                r, c, player_id = map(int, payload.split('|'))
                self.locked_squares[(r, c)] = player_id
                if self.pending_lock_request == (r, c) and player_id != self.my_player_id:
                    self.set_status(f"Square ({r},{c}) locked by other player.", COLOR_STATUS_INFO)
                    self.pending_lock_request = None

            # Update scribbles from other players
            elif command == "PLAYER_SCRIBBLE":
                try:
                    parts = payload.split('|')
                    r, c, player_id = int(parts[0]), int(parts[1]), int(parts[2])
                    x, y = int(parts[3]), int(parts[4])

                    if (r, c) not in self.other_players_scribbles:
                        self.other_players_scribbles[(r, c)] = {'player_id': player_id, 'points': []}

                    self.other_players_scribbles[(r, c)]['points'].append((x, y))
                except Exception as e:
                    print(f"Error processing PLAYER_SCRIBBLE: {e}, payload: {payload}")

            #  Handle scribble unlocks
            elif command == "SQUARE_UNLOCKED":
                r, c = map(int, payload.split('|'))
                if (r, c) in self.locked_squares:
                    del self.locked_squares[(r, c)]
                # Clear any scribbles for this square when unlocked
                if (r, c) in self.other_players_scribbles:
                    del self.other_players_scribbles[(r, c)]
                if self.pending_lock_request == (r, c):
                    self.set_status(f"Square ({r},{c}) unlocked.", COLOR_STATUS_INFO)
                    self.pending_lock_request = None
                    # Clear any scribble points if we were waiting for this square
                    self.grid.scribble_points = []
                    self.grid.scribble_coverage_pixels.clear()

            # Show information status messages such as game over and errors
            elif command == "INFO":
                self.log_message(f"Info: {payload}")
            elif command == "ERROR":
                self.set_status(f"Server Error: {payload}", COLOR_STATUS_ERROR)
                self.log_message(f"Error: {payload}")
            elif command == "GAME_OVER":
                self.game_over = True
                self.is_scribbling = False
                self.game_over_message = payload
                self.set_status(f"{self.game_over_message}", COLOR_STATUS_SUCCESS)
                self.log_message(f"--- {self.game_over_message} ---")

                # Schedule client shutdown after 20 seconds
                print("Client will shut down in 20 seconds...")
                threading.Timer(20, self.on_closing).start()

            # Update timer
            elif command == "TIMER_UPDATE":
                self.remaining_time = int(payload)
                print(f"Timer updated: {self.remaining_time} seconds remaining")

        except Exception as e:
            self.log_message(f"Error processing msg '{message}': {e}")
            import traceback

            traceback.print_exc()

    def handle_disconnection(self, reason):
        """Handle disconnection from the server."""
        if self.connected:
            self.connected = False
            self.log_message(f"Disconnected: {reason}")
            self.set_status(f"Disconnected: {reason}", COLOR_STATUS_ERROR)
            self.cleanup_connection()
            self.current_scene = "login"

    def cleanup_connection(self):
        """Clean up the connection."""
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                print(f"Error closing socket: {e}")
            self.sock = None
        self.my_player_id = -1
        self.is_scribbling = False
        self.pending_lock_request = None

    def send_message(self, message):
        """Send a message to the server."""
        if not self.connected or not self.sock:
            self.log_message("Cannot send message: not connected.")
            return False
        try:
            # Make sure the message ends with a newline
            if not message.endswith('\n'):
                message += '\n'
            self.sock.sendall(message.encode('utf-8'))
            return True
        except Exception as e:
            self.log_message(f"Error sending message: {e}")
            self.handle_disconnection(f"Send error: {e}")
            return False

    def set_status(self, text, color):
        """Set the status text and color."""
        self.status_text = text
        self.status_color = color

    def log_message(self, message):
        """Log a message to the console and store it."""
        print(f"LOG: {message}")
        if not hasattr(self, '_log_messages'):
            self._log_messages = []
        self._log_messages.append(message)
        if len(self._log_messages) > 10:
            self._log_messages.pop(0)

    def start_queue_processing(self):
        """Process the message queue in a separate thread."""
        self.process_queue()

    def run(self):
        """Main game loop."""
        running = True
        while running:
            self.process_queue()

            # Handle events for login and game scenes
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif self.current_scene == "login":
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        self.login.handle_mouse_click(event.pos)
                    elif event.type == pygame.KEYDOWN:
                        self.login.handle_key_press(event)
                elif self.current_scene == "game":
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        self.grid.handle_mouse_down(event.pos)
                    elif event.type == pygame.MOUSEMOTION:
                        self.grid.handle_mouse_motion(event.pos)
                    elif event.type == pygame.MOUSEBUTTONUP:
                        self.grid.handle_mouse_up()

            if self.current_scene == "login":
                self.login.draw(self.screen)
            elif self.current_scene == "game":
                self.screen.fill(COLOR_WHITE)

                status_rect = pygame.Rect(0, 0, SCREEN_WIDTH, 50)
                pygame.draw.rect(self.screen, COLOR_LIGHT_GREY, status_rect)
                status_surf = self.font_status.render(self.status_text, True, self.status_color)
                status_pos = status_surf.get_rect(center=(SCREEN_WIDTH // 2, status_rect.height // 2))
                self.screen.blit(status_surf, status_pos)

                timer_text = f"Time Left: {self.remaining_time // 60}:{self.remaining_time % 60:02d}"
                timer_surf = self.font_status.render(timer_text, True, COLOR_BLACK)
                timer_pos = timer_surf.get_rect(midright=(SCREEN_WIDTH - 10, 25))
                self.screen.blit(timer_surf, timer_pos)

                self.grid.draw(self.screen)

                player_list_x = GRID_TOP_LEFT[0] + GRID_AREA_SIZE + 20
                player_list_y = GRID_TOP_LEFT[1] + (GRID_AREA_SIZE // 2) - (len(self.players) * 30 // 2)

                # Show player list
                for player_id, player_info in self.players.items():
                    color = self.hex_to_rgb(player_info['color'])
                    name = player_info['name']
                    is_you = "(You)" if player_id == self.my_player_id else ""

                    # Get the player's score from the board
                    score = sum(row.count(player_id) for row in self.board)

                    swatch_rect = pygame.Rect(player_list_x, player_list_y, 20, 20)
                    pygame.draw.rect(self.screen, color, swatch_rect)
                    pygame.draw.rect(self.screen, COLOR_BLACK, swatch_rect, 1)

                    name_text = f"{name} {is_you} - {score} pts"
                    name_surf = self.font_ui.render(name_text, True, COLOR_BLACK)
                    self.screen.blit(name_surf, (player_list_x + 30, player_list_y))

                    player_list_y += 30

            pygame.display.flip()
            self.clock.tick(60)

        self.on_closing()

    def on_closing(self):
        """Handle window closing."""
        print("Closing client...")
        if self.connected:
            self.send_message("DISCONNECT\n")
            time.sleep(0.1)
        self.connected = False
        self.cleanup_connection()
        pygame.quit()
        sys.exit(0)


if __name__ == "__main__":
    client_app = GameClient()
    client_app.run()
