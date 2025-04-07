import socket
import threading
import pygame
import queue
import ast
import time
import sys

# --- Constants ---
BUFFER_SIZE = 4096
TARGET_COVERAGE = 0.50 # Deny & Conquer Rule

# --- Pygame Settings ---
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
GRID_AREA_SIZE = 480 # Pixel size of the playable grid area
GRID_TOP_LEFT = (50, 70) # Top-left corner of the grid on screen
INFO_AREA_TOP_LEFT = (GRID_TOP_LEFT[0] + GRID_AREA_SIZE + 30, GRID_TOP_LEFT[1])
INFO_AREA_WIDTH = SCREEN_WIDTH - INFO_AREA_TOP_LEFT[0] - 30

# --- Colors ---
COLOR_WHITE = (255, 255, 255)
COLOR_BLACK = (0, 0, 0)
COLOR_LIGHT_GREY = (211, 211, 211)
COLOR_DARK_GREY = (100, 100, 100)
COLOR_GRID_LINE = (180, 180, 180)
COLOR_SCRIBBLE = (50, 50, 50) # Dark grey for scribble lines
COLOR_INPUT_BG = (240, 240, 240)
COLOR_INPUT_BORDER = (150, 150, 150)
COLOR_INPUT_BORDER_ACTIVE = (0, 120, 215)
COLOR_BUTTON = (0, 120, 215)
COLOR_BUTTON_TEXT = COLOR_WHITE
COLOR_STATUS_INFO = (50, 50, 150)
COLOR_STATUS_ERROR = (180, 50, 50)
COLOR_STATUS_SUCCESS = (50, 150, 50)

# Alpha values for lock indicators (0-255)
ALPHA_LOCK_SELF = 100
ALPHA_LOCK_OTHER = 100

# --- Helper Function for Alpha Rects ---
def draw_rect_alpha(surface, color_rgb, alpha, rect):
    shape_surf = pygame.Surface(pygame.Rect(rect).size, pygame.SRCALPHA)
    pygame.draw.rect(shape_surf, color_rgb + (alpha,), shape_surf.get_rect())
    surface.blit(shape_surf, rect)

# --- Game Client Class ---
class GameClient:
    def __init__(self):
        pygame.init()
        pygame.font.init()

        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Deny & Conquer Client (Pygame)")
        self.clock = pygame.time.Clock()

        # --- Fonts ---
        try:
            self.font_ui = pygame.font.SysFont("Segoe UI", 16)
            self.font_ui_small = pygame.font.SysFont("Segoe UI", 14)
            self.font_title = pygame.font.SysFont("Segoe UI", 24, bold=True)
            self.font_status = pygame.font.SysFont("Segoe UI", 18)
            self.font_lock = pygame.font.SysFont("Arial", 10) # Smaller for lock text
        except pygame.error:
             print("Warning: Segoe UI font not found, using default Arial.")
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
        self.server_port = "65433" # Deny & Conquer port
        self.my_player_id = -1
        self.my_color_tuple = (0, 0, 0) # Pygame color tuple
        self.my_color_str = 'black'     # Original string for reference
        self.grid_size = 8
        self.board = []
        self.players = {} # {id: {'name': name, 'color': hex_str}}
        self.scores = {}
        self.locked_squares = {} # (r, c): player_id
        self.game_over = False
        self.game_over_message = ""
        self.status_text = "Enter details and connect."
        self.status_color = COLOR_STATUS_INFO

        # --- Scribbling State ---
        self.is_scribbling = False
        self.scribble_square = None # (r, col)
        self.scribble_points = [] # Store points for drawing lines [(x,y), (x,y), ...]
        self.scribble_coverage_pixels = set() # Store (x,y) screen coords covered
        self.square_pixel_size = GRID_AREA_SIZE / self.grid_size
        self.total_pixels_in_square = self.square_pixel_size ** 2
        self.pending_lock_request = None # (r,c)

        # --- Scene Management ---
        self.current_scene = "login" # "login" or "game"

        # --- Login Scene UI Elements ---
        self.input_fields = {
            "name": {"rect": pygame.Rect(250, 200, 300, 30), "text": self.player_name, "label": "Player Name:"},
            "ip": {"rect": pygame.Rect(250, 250, 300, 30), "text": self.server_ip, "label": "Server IP:"},
            "port": {"rect": pygame.Rect(250, 300, 300, 30), "text": self.server_port, "label": "Server Port:"},
        }
        self.active_field = None # Key of the active input field ("name", "ip", "port")
        self.connect_button_rect = pygame.Rect(300, 360, 200, 40)

        # Start processing network messages immediately
        self.start_queue_processing()

    def start_queue_processing(self):
         """ Check queue periodically without dedicated thread """
         self.process_queue() # Process once immediately
         # In pygame, we call process_queue within the main loop, no need for root.after

    def hex_to_rgb(self, hex_color):
        """Converts a hex color string like '#FF0000' to an RGB tuple (255, 0, 0)."""
        hex_color = hex_color.lstrip('#')
        try:
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        except ValueError:
            print(f"Warning: Invalid color hex {hex_color}, using black.")
            return (0, 0, 0) # Default to black on error

    # === Network Handling (Similar to Tkinter version) ===

    def connect_to_game(self):
        self.player_name = self.input_fields["name"]["text"]
        self.server_ip = self.input_fields["ip"]["text"]
        self.server_port = self.input_fields["port"]["text"]

        if not self.player_name: self.set_status("Player Name cannot be empty.", COLOR_STATUS_ERROR); return
        if not self.server_ip: self.set_status("Server IP cannot be empty.", COLOR_STATUS_ERROR); return
        try:
            port_num = int(self.server_port)
            if not (1024 < port_num < 65536): raise ValueError("Port out of range")
        except ValueError: self.set_status("Invalid Port number (1025-65535).", COLOR_STATUS_ERROR); return

        try:
            self.set_status(f"Connecting to {self.server_ip}:{self.server_port}...", COLOR_STATUS_INFO)
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Optional: Set timeout
            # self.sock.settimeout(5.0)
            self.sock.connect((self.server_ip, port_num))
            # self.sock.settimeout(None) # Reset timeout
            self.connected = True
            self.game_over = False
            self.game_over_message = ""

            connect_msg = f"CONNECT|{self.player_name}\n"
            self.sock.sendall(connect_msg.encode('utf-8'))

            self.receive_thread = threading.Thread(target=self.receive_messages, daemon=True)
            self.receive_thread.start()
            self.log_message(f"Connection attempt initiated...")
            # Scene change happens upon receiving WELCOME message

        except ConnectionRefusedError: self.set_status(f"Connection refused. Server offline?", COLOR_STATUS_ERROR); self.cleanup_connection()
        except socket.timeout: self.set_status(f"Connection timed out.", COLOR_STATUS_ERROR); self.cleanup_connection()
        except socket.gaierror: self.set_status(f"Could not resolve hostname.", COLOR_STATUS_ERROR); self.cleanup_connection()
        except Exception as e: self.set_status(f"Connection failed: {e}", COLOR_STATUS_ERROR); self.cleanup_connection()


    def receive_messages(self):
        buffer = ""
        while self.connected and self.sock:
            try:
                data = self.sock.recv(BUFFER_SIZE)
                if not data: self.message_queue.put(("DISCONNECT", "Server closed connection.")); break
                buffer += data.decode('utf-8')
                while '\n' in buffer:
                    message, buffer = buffer.split('\n', 1)
                    if message: self.message_queue.put(("MESSAGE", message.strip()))
            except ConnectionResetError: self.message_queue.put(("DISCONNECT", "Connection reset.")); break
            except socket.timeout: self.log_message("Network receive timeout (expected during inactivity)."); continue # Ignore timeout
            except OSError as e:
                 if self.connected: self.message_queue.put(("DISCONNECT", f"Network error: {e}"))
                 break
            except Exception as e:
                 if self.connected: self.message_queue.put(("DISCONNECT", f"Receive error: {e}"))
                 break
        self.connected = False; print("Receive thread finished.")

    def process_queue(self):
        """ Process messages from the queue - Called in main loop """
        try:
            while not self.message_queue.empty():
                msg_type, data = self.message_queue.get_nowait()
                if msg_type == "MESSAGE": self.handle_server_message(data)
                elif msg_type == "DISCONNECT": self.handle_disconnection(data)
        except queue.Empty:
            pass
        # No rescheduling needed like root.after

    def handle_server_message(self, message):
        """ Parses messages and updates state """
        print(f"Received: {message}")
        try:
            parts = message.split('|', 1)
            command = parts[0]
            payload = parts[1] if len(parts) > 1 else ""

            if command == "WELCOME":
                p_parts = payload.split('|')
                self.my_player_id = int(p_parts[0])
                self.my_color_str = p_parts[1]
                self.my_color_tuple = self.hex_to_rgb(self.my_color_str)
                self.grid_size = int(p_parts[2])
                pygame.display.set_caption(f"Deny & Conquer - {self.player_name} (ID: {self.my_player_id})")
                self.log_message(f"Connected! Your color: {self.my_color_str}")
                # --- Switch to Game Scene ---
                self.current_scene = "game"
                self.board = [[0] * self.grid_size for _ in range(self.grid_size)]
                self.calculate_square_size()
                self.set_status("Game started! Click white squares.", COLOR_STATUS_INFO)

            elif command == "UPDATE_BOARD":
                 self.board = ast.literal_eval(payload)
                 # No explicit redraw here, happens in game loop drawing phase

            elif command == "UPDATE_PLAYERS":
                 self.players = ast.literal_eval(payload)

            elif command == "UPDATE_SCORES":
                 self.scores = ast.literal_eval(payload)

            elif command == "LOCK_GRANTED":
                 r, c = map(int, payload.split('|'))
                 if self.pending_lock_request == (r, c):
                     print(f"Lock granted for ({r},{c})")
                     self.is_scribbling = True
                     self.scribble_square = (r, c)
                     self.scribble_points = [] # Start new line list
                     self.scribble_coverage_pixels.clear()
                     self.locked_squares[(r, c)] = self.my_player_id # Show lock immediately
                     self.set_status(f"Scribbling in ({r},{c})...", COLOR_STATUS_INFO)
                 else: print(f"WARN: LOCK_GRANTED for unexpected square ({r},{c})")
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

            elif command == "SQUARE_UNLOCKED":
                 r, c = map(int, payload.split('|'))
                 if (r, c) in self.locked_squares: del self.locked_squares[(r, c)]
                 if self.pending_lock_request == (r, c):
                     self.set_status(f"Square ({r},{c}) unlocked.", COLOR_STATUS_INFO)
                     self.pending_lock_request = None

            elif command == "INFO": self.log_message(f"Info: {payload}")
            elif command == "ERROR": self.set_status(f"Server Error: {payload}", COLOR_STATUS_ERROR); self.log_message(f"Error: {payload}")

            elif command == "GAME_OVER":
                 self.game_over = True
                 self.is_scribbling = False
                 self.game_over_message = payload
                 self.set_status(f"GAME OVER! {self.game_over_message}", COLOR_STATUS_SUCCESS)
                 self.log_message(f"--- {self.game_over_message} ---")

        except Exception as e: self.log_message(f"Error processing msg '{message}': {e}"); import traceback; traceback.print_exc()


    def handle_disconnection(self, reason):
        if self.connected:
            self.connected = False
            self.log_message(f"Disconnected: {reason}")
            # Show message box? Or just status text?
            # messagebox.showinfo("Disconnected", f"Lost connection.\n{reason}") # Pygame has no messagebox
            self.set_status(f"Disconnected: {reason}", COLOR_STATUS_ERROR)
            self.cleanup_connection()
            # Return to login screen
            self.current_scene = "login"


    def cleanup_connection(self):
        self.connected = False
        if self.sock:
            try: self.sock.close()
            except Exception as e: print(f"Error closing socket: {e}")
            self.sock = None
        # Reset relevant game state for login screen
        self.my_player_id = -1
        self.is_scribbling = False
        self.pending_lock_request = None
        # Keep player name/ip/port entered previously


    def send_message(self, message):
        if self.connected and self.sock:
            try: print(f"Sending: {message.strip()}"); self.sock.sendall(message.encode('utf-8'))
            except (BrokenPipeError, ConnectionResetError, OSError) as e: self.message_queue.put(("DISCONNECT", f"Send error: {e}"))
            except Exception as e: self.log_message(f"Unexpected send error: {e}")
        elif not self.game_over: self.log_message("Cannot send: Not connected.")

    def set_status(self, text, color):
         self.status_text = text
         self.status_color = color

    def log_message(self, message):
         # In pygame, we'd need to render log messages to a surface or manage a list
         # For simplicity, just print to console for now
         print(f"LOG: {message}")

    # === Coordinate Conversion ===

    def calculate_square_size(self):
         if self.grid_size > 0:
              self.square_pixel_size = GRID_AREA_SIZE / self.grid_size
              self.total_pixels_in_square = self.square_pixel_size ** 2

    def coords_to_grid(self, screen_x, screen_y):
        """ Convert screen x, y coordinates to grid row, col """
        if not (GRID_TOP_LEFT[0] <= screen_x < GRID_TOP_LEFT[0] + GRID_AREA_SIZE and
                GRID_TOP_LEFT[1] <= screen_y < GRID_TOP_LEFT[1] + GRID_AREA_SIZE):
            return None, None # Click outside grid area

        local_x = screen_x - GRID_TOP_LEFT[0]
        local_y = screen_y - GRID_TOP_LEFT[1]

        col = int(local_x // self.square_pixel_size)
        row = int(local_y // self.square_pixel_size)
        col = max(0, min(col, self.grid_size - 1))
        row = max(0, min(row, self.grid_size - 1))
        return row, col

    def grid_to_screen_rect(self, r, c):
         """ Convert grid row, col to screen Rect """
         x0 = GRID_TOP_LEFT[0] + c * self.square_pixel_size
         y0 = GRID_TOP_LEFT[1] + r * self.square_pixel_size
         return pygame.Rect(x0, y0, self.square_pixel_size, self.square_pixel_size)

    # === Drawing Functions ===

    def draw_login_scene(self):
        self.screen.fill(COLOR_WHITE)
        title_surf = self.font_title.render("Deny & Conquer", True, COLOR_BLACK)
        self.screen.blit(title_surf, (SCREEN_WIDTH // 2 - title_surf.get_width() // 2, 100))

        # Draw Input Fields
        for key, field in self.input_fields.items():
            # Draw Label
            label_surf = self.font_ui.render(field["label"], True, COLOR_BLACK)
            label_rect = label_surf.get_rect(midright=(field["rect"].left - 10, field["rect"].centery))
            self.screen.blit(label_surf, label_rect)

            # Draw Input Box
            border_color = COLOR_INPUT_BORDER_ACTIVE if self.active_field == key else COLOR_INPUT_BORDER
            pygame.draw.rect(self.screen, COLOR_INPUT_BG, field["rect"])
            pygame.draw.rect(self.screen, border_color, field["rect"], 1)

            # Draw Text Inside Box
            text_surf = self.font_ui.render(field["text"], True, COLOR_BLACK)
            text_rect = text_surf.get_rect(midleft=(field["rect"].left + 5, field["rect"].centery))
            self.screen.blit(text_surf, text_rect)

        # Draw Connect Button
        pygame.draw.rect(self.screen, COLOR_BUTTON, self.connect_button_rect, border_radius=5)
        btn_text_surf = self.font_ui.render("Connect", True, COLOR_BUTTON_TEXT)
        btn_text_rect = btn_text_surf.get_rect(center=self.connect_button_rect.center)
        self.screen.blit(btn_text_surf, btn_text_rect)

        # Draw Status Message
        status_surf = self.font_ui_small.render(self.status_text, True, self.status_color)
        status_rect = status_surf.get_rect(center=(SCREEN_WIDTH // 2, 450))
        self.screen.blit(status_surf, status_rect)


    def draw_game_scene(self):
        self.screen.fill(COLOR_WHITE)

        # --- Draw Status Bar ---
        status_rect = pygame.Rect(0, 0, SCREEN_WIDTH, 50)
        pygame.draw.rect(self.screen, COLOR_LIGHT_GREY, status_rect)
        status_surf = self.font_status.render(self.status_text, True, self.status_color)
        status_pos = status_surf.get_rect(center=(SCREEN_WIDTH // 2, status_rect.height // 2))
        self.screen.blit(status_surf, status_pos)

        # --- Draw Grid Area Background ---
        grid_bg_rect = pygame.Rect(GRID_TOP_LEFT[0], GRID_TOP_LEFT[1], GRID_AREA_SIZE, GRID_AREA_SIZE)
        pygame.draw.rect(self.screen, COLOR_DARK_GREY, grid_bg_rect, 1) # Border

        # --- Draw Squares ---
        if self.board:
            for r in range(self.grid_size):
                for c in range(self.grid_size):
                    player_id = self.board[r][c]
                    square_rect = self.grid_to_screen_rect(r, c)
                    fill_color = COLOR_WHITE
                    outline_color = COLOR_GRID_LINE

                    if player_id != 0:
                         player_info = self.players.get(player_id)
                         if player_info:
                              fill_color = self.hex_to_rgb(player_info['color'])
                         else:
                              fill_color = COLOR_DARK_GREY # Unknown player claimed
                         outline_color = COLOR_BLACK

                    pygame.draw.rect(self.screen, fill_color, square_rect)
                    # Don't draw outline if white, let grid lines show
                    if fill_color != COLOR_WHITE:
                         pygame.draw.rect(self.screen, outline_color, square_rect, 1)

        # --- Draw Grid Lines ---
        for i in range(1, self.grid_size):
            # Vertical
            x = GRID_TOP_LEFT[0] + i * self.square_pixel_size
            pygame.draw.line(self.screen, COLOR_GRID_LINE, (x, GRID_TOP_LEFT[1]), (x, GRID_TOP_LEFT[1] + GRID_AREA_SIZE))
            # Horizontal
            y = GRID_TOP_LEFT[1] + i * self.square_pixel_size
            pygame.draw.line(self.screen, COLOR_GRID_LINE, (GRID_TOP_LEFT[0], y), (GRID_TOP_LEFT[0] + GRID_AREA_SIZE, y))

        # --- Draw Scribble Lines ---
        if self.is_scribbling and len(self.scribble_points) > 1:
            pygame.draw.lines(self.screen, COLOR_SCRIBBLE, False, self.scribble_points, 3) # Adjust thickness (width=3)

        # --- Draw Lock Indicators ---
        for (r, c), player_id in self.locked_squares.items():
             square_rect = self.grid_to_screen_rect(r, c)
             player_info = self.players.get(player_id)
             lock_color_rgb = COLOR_DARK_GREY # Default if player unknown
             alpha = ALPHA_LOCK_OTHER
             text_prefix = f"P{player_id}" # Default text

             if player_info:
                  lock_color_rgb = self.hex_to_rgb(player_info['color'])
                  text_prefix = player_info['name']

             if player_id == self.my_player_id:
                  alpha = ALPHA_LOCK_SELF
                  text_prefix = "You"

             # Draw semi-transparent overlay
             draw_rect_alpha(self.screen, lock_color_rgb, alpha, square_rect)

             # Draw "Locked by" text (optional, can get cluttered)
             # lock_text = f"Locked by {text_prefix}"
             # text_surf = self.font_lock.render(lock_text, True, COLOR_WHITE) # White text on overlay
             # text_rect = text_surf.get_rect(center=square_rect.center)
             # self.screen.blit(text_surf, text_rect)


        # --- Draw Info Area (Players & Scores) ---
        info_x = INFO_AREA_TOP_LEFT[0]
        info_y = INFO_AREA_TOP_LEFT[1]

        title_surf = self.font_ui.render("Players & Scores", True, COLOR_BLACK)
        self.screen.blit(title_surf, (info_x, info_y))
        info_y += title_surf.get_height() + 10

        if not self.players:
             no_players_surf = self.font_ui_small.render("No players yet.", True, COLOR_DARK_GREY)
             self.screen.blit(no_players_surf, (info_x, info_y))
        else:
             sorted_players = sorted(self.players.items(), key=lambda item: self.scores.get(item[0], 0), reverse=True)
             for p_id, player_info in sorted_players:
                 score = self.scores.get(p_id, 0)
                 player_name = player_info['name']
                 player_color_str = player_info['color']
                 player_color_rgb = self.hex_to_rgb(player_color_str)
                 you_marker = " (You)" if p_id == self.my_player_id else ""

                 # Draw color swatch
                 swatch_rect = pygame.Rect(info_x, info_y, 15, 15)
                 pygame.draw.rect(self.screen, player_color_rgb, swatch_rect)
                 pygame.draw.rect(self.screen, COLOR_BLACK, swatch_rect, 1) # Border

                 # Draw text
                 display_text = f"{player_name}{you_marker}: {score}"
                 player_surf = self.font_ui_small.render(display_text, True, COLOR_BLACK)
                 self.screen.blit(player_surf, (info_x + 20, info_y)) # Offset for swatch
                 info_y += player_surf.get_height() + 5 # Spacing


    # === Event Handling ===

    def handle_login_events(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            # Check connect button
            if self.connect_button_rect.collidepoint(event.pos):
                self.connect_to_game()
                return # Don't check input fields if button clicked

            # Check input fields
            self.active_field = None
            for key, field in self.input_fields.items():
                if field["rect"].collidepoint(event.pos):
                    self.active_field = key
                    print(f"Activated field: {key}")
                    break

        elif event.type == pygame.KEYDOWN:
            if self.active_field:
                field = self.input_fields[self.active_field]
                if event.key == pygame.K_BACKSPACE:
                    field["text"] = field["text"][:-1]
                elif event.key == pygame.K_RETURN:
                     if self.active_field == "port": # Try connecting on Enter in last field
                          self.connect_to_game()
                     else: # Move to next field (simple logic)
                          keys = list(self.input_fields.keys())
                          try:
                               next_index = keys.index(self.active_field) + 1
                               if next_index < len(keys): self.active_field = keys[next_index]
                               else: self.active_field = None # Deactivate if last
                          except ValueError: self.active_field = None
                else:
                    # Append unicode character if printable
                    if event.unicode.isprintable():
                        field["text"] += event.unicode


    def handle_game_events(self, event):
         if event.type == pygame.MOUSEBUTTONDOWN:
              if event.button == 1: # Left click
                   if self.game_over or not self.connected: return
                   if self.is_scribbling: return # Should not happen if logic correct

                   r, c = self.coords_to_grid(event.pos[0], event.pos[1])
                   if r is not None: # Click was inside grid
                        is_white = self.board[r][c] == 0
                        is_locked = (r, c) in self.locked_squares

                        if is_white and not is_locked:
                             self.set_status(f"Requesting lock for ({r},{c})...", COLOR_STATUS_INFO)
                             self.pending_lock_request = (r, c)
                             self.send_message(f"LOCK_REQUEST|{r}|{c}\n")
                        elif not is_white:
                             self.set_status(f"Square ({r},{c}) already taken.", COLOR_STATUS_INFO)
                        elif is_locked:
                             locker_id = self.locked_squares.get((r,c))
                             locker_name = self.players.get(locker_id, {}).get('name', f'P{locker_id}')
                             self.set_status(f"Square ({r},{c}) locked by {locker_name}.", COLOR_STATUS_INFO)

         elif event.type == pygame.MOUSEMOTION:
              if self.is_scribbling and self.scribble_square is not None:
                   current_pos = event.pos
                   # Check if motion is within the scribble square bounds for accuracy
                   r_curr, c_curr = self.coords_to_grid(current_pos[0], current_pos[1])
                   if (r_curr, c_curr) == self.scribble_square:
                        # Add point for drawing line segments
                        self.scribble_points.append(current_pos)
                        # Add coverage pixels (simple method)
                        radius = 3 # Simulate pen thickness for coverage check
                        for dx in range(-radius, radius + 1):
                             for dy in range(-radius, radius + 1):
                                  # Optional: Check distance for circle: if dx*dx + dy*dy <= radius*radius:
                                  px, py = int(current_pos[0]+dx), int(current_pos[1]+dy)
                                  # Add only if within the specific square's screen rect
                                  sq_rect = self.grid_to_screen_rect(self.scribble_square[0], self.scribble_square[1])
                                  if sq_rect.collidepoint(px, py):
                                       self.scribble_coverage_pixels.add((px, py))


         elif event.type == pygame.MOUSEBUTTONUP:
              if event.button == 1: # Left click release
                   if self.is_scribbling and self.scribble_square is not None:
                        r, c = self.scribble_square
                        print(f"Released mouse in ({r},{c})")

                        coverage = 0
                        if self.total_pixels_in_square > 0:
                             coverage = len(self.scribble_coverage_pixels) / self.total_pixels_in_square
                        self.log_message(f"Square ({r},{c}): Covered ~{len(self.scribble_coverage_pixels)} pixels, Coverage ~{coverage:.2%}")

                        if coverage >= TARGET_COVERAGE:
                             self.log_message(f"Attempting claim ({r},{c})")
                             self.send_message(f"CLAIM_ATTEMPT|{r}|{c}\n")
                             self.set_status(f"Attempting claim for ({r},{c})...", COLOR_STATUS_SUCCESS)
                        else:
                             self.log_message(f"Releasing lock ({r},{c}) - Low coverage")
                             self.send_message(f"RELEASE_LOCK|{r}|{c}\n")
                             self.set_status(f"Claim failed for ({r},{c}) - <50% coverage.", COLOR_STATUS_INFO)

                        # Cleanup scribble state
                        self.is_scribbling = False
                        self.scribble_square = None
                        self.scribble_points = []
                        self.scribble_coverage_pixels.clear()
                        # Lock indicator removed by server response (SQUARE_UNLOCKED or UPDATE_BOARD)

                   elif self.pending_lock_request:
                        # Mouse released before lock granted/denied
                        print("Mouse released while lock pending.")
                        self.pending_lock_request = None
                        self.set_status("Lock request cancelled.", COLOR_STATUS_INFO)

    # === Main Loop ===

    def run(self):
        running = True
        while running:
            # --- Process Network Messages ---
            self.process_queue()

            # --- Handle Events ---
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if self.current_scene == "login":
                    self.handle_login_events(event)
                elif self.current_scene == "game":
                    self.handle_game_events(event)

            # --- Drawing ---
            if self.current_scene == "login":
                self.draw_login_scene()
            elif self.current_scene == "game":
                self.draw_game_scene()

            # --- Update Display ---
            pygame.display.flip()

            # --- Cap Framerate ---
            self.clock.tick(60) # Limit to 60 FPS

        # --- Exit ---
        self.on_closing()

    def on_closing(self):
         print("Closing client...")
         if self.connected:
              self.send_message("DISCONNECT\n")
              time.sleep(0.1) # Brief pause
         self.connected = False
         self.cleanup_connection()
         pygame.quit()
         sys.exit()


# --- Run the App ---
if __name__ == "__main__":
    client_app = GameClient()
    client_app.run()