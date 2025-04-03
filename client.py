import socket
import threading
import tkinter as tk
from tkinter import messagebox
import queue
import ast
import time
import sys

BUFFER_SIZE = 4096
TARGET_COVERAGE = 0.50
SCRIBBLE_COLOR = "#C0C0C0"
LOCK_INDICATOR_COLOR_SELF = "#A0A0FFC0"
LOCK_INDICATOR_COLOR_OTHER = "#FFA0A0C0"

class GameClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Deny & Conquer Client")
        self.root.geometry("650x550")

        self.sock = None
        self.player_name = None
        self.my_player_id = -1
        self.my_color = 'black'
        self.grid_size = 8
        self.receive_thread = None
        self.connected = False
        self.message_queue = queue.Queue()

        self.board = []
        self.players = {}
        self.scores = {}
        self.locked_squares = {}
        self.game_over = False

        self.login_frame = None
        self.game_frame = None
        self.canvas = None
        self.status_label = None
        self.players_scores_label = None
        self.log_area = None
        self.canvas_squares = {}
        self.lock_indicators = {}

        self.is_scribbling = False
        self.scribble_square = None
        self.scribble_pixels = set()
        self.scribble_lines = []
        self.square_pixel_size = 50
        self.total_pixels_in_square = 2500

        self.pending_lock_request = None

        self.create_login_widgets()
        self.root.after(100, self.process_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_login_widgets(self):
        if self.game_frame: self.game_frame.pack_forget()
        self.login_frame = tk.Frame(self.root, padx=10, pady=10)
        self.login_frame.pack(expand=True)

        tk.Label(self.login_frame, text="Player Name:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.name_entry = tk.Entry(self.login_frame, width=20)
        self.name_entry.grid(row=0, column=1, pady=5)

        tk.Label(self.login_frame, text="Server IP:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.ip_entry = tk.Entry(self.login_frame, width=20)
        self.ip_entry.grid(row=1, column=1, pady=5)
        self.ip_entry.insert(0, "127.0.0.1")

        tk.Label(self.login_frame, text="Server Port:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.port_entry = tk.Entry(self.login_frame, width=20)
        self.port_entry.grid(row=2, column=1, pady=5)
        self.port_entry.insert(0, "65433")

        self.connect_button = tk.Button(self.login_frame, text="Connect to Game", command=self.connect_to_game)
        self.connect_button.grid(row=3, column=0, columnspan=2, pady=20)

        tk.Label(self.login_frame, text="If hosting, run server.py first, then connect.").grid(row=4, column=0, columnspan=2, pady=5)

    def create_game_widgets(self):
        if self.login_frame: self.login_frame.pack_forget()
        self.game_frame = tk.Frame(self.root, padx=5, pady=5)
        self.game_frame.pack(expand=True, fill=tk.BOTH)

        left_frame = tk.Frame(self.game_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

        right_frame = tk.Frame(self.game_frame, width=200)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5)
        right_frame.pack_propagate(False)

        canvas_size = 400
        self.canvas = tk.Canvas(left_frame, width=canvas_size, height=canvas_size, bg='white', borderwidth=1, relief="sunken")
        self.canvas.pack(pady=5)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

        self.status_label = tk.Label(left_frame, text="Connecting...", wraplength=canvas_size, justify=tk.LEFT)
        self.status_label.pack(fill=tk.X, pady=5)

        tk.Label(right_frame, text="Players & Scores:", font=("Arial", 10, "bold")).pack(anchor=tk.NW)
        self.players_scores_label = tk.Label(right_frame, text="", justify=tk.LEFT, anchor=tk.NW)
        self.players_scores_label.pack(fill=tk.X, pady=5)

    def log_message(self, message):
        if self.log_area:
            self.log_area.config(state=tk.NORMAL)
            self.log_area.insert(tk.END, message + "\n")
            self.log_area.see(tk.END)
            self.log_area.config(state=tk.DISABLED)

    def connect_to_game(self):
        self.player_name = self.name_entry.get().strip()
        server_ip = self.ip_entry.get().strip()
        server_port_str = self.port_entry.get().strip()

        if not self.player_name: messagebox.showerror("Error", "Player Name cannot be empty."); return
        if not server_ip: messagebox.showerror("Error", "Server IP cannot be empty."); return
        try:
            server_port = int(server_port_str)
            if not (1024 < server_port < 65536): raise ValueError("Port out of range")
        except ValueError: messagebox.showerror("Error", "Invalid Port number (1025-65535)."); return

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((server_ip, server_port))
            self.connected = True
            self.game_over = False

            connect_msg = f"CONNECT|{self.player_name}\n"
            self.sock.sendall(connect_msg.encode('utf-8'))

            self.receive_thread = threading.Thread(target=self.receive_messages, daemon=True)
            self.receive_thread.start()

            self.log_message(f"Attempting connection to {server_ip}:{server_port} as {self.player_name}")

        except ConnectionRefusedError: messagebox.showerror("Connection Error", f"Connection refused. Server running at {server_ip}:{server_port}?"); self.connected = False; self.sock = None
        except socket.gaierror: messagebox.showerror("Connection Error", f"Could not resolve hostname: {server_ip}"); self.connected = False; self.sock = None
        except Exception as e: messagebox.showerror("Error", f"Connection failed: {e}"); self.connected = False; self.cleanup_connection()

    def receive_messages(self):
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
                    if message: self.message_queue.put(("MESSAGE", message.strip()))
            except ConnectionResetError: self.message_queue.put(("DISCONNECT", "Connection reset by server.")); break
            except OSError as e:
                if self.connected:
                    self.message_queue.put(("DISCONNECT", f"Network error: {e}"))
                break
            except Exception as e:
                if self.connected:
                    self.message_queue.put(("DISCONNECT", f"Error receiving data: {e}"))
                break
        self.connected = False
        print("Receive thread finished.")

    def process_queue(self):
        try:
            while not self.message_queue.empty():
                msg_type, data = self.message_queue.get_nowait()
                if msg_type == "MESSAGE": self.handle_server_message(data)
                elif msg_type == "DISCONNECT": self.handle_disconnection(data)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_queue)

    def handle_server_message(self, message):
        print(f"GUI received: {message}")
        try:
            parts = message.split('|', 1)
            command = parts[0]
            payload = parts[1] if len(parts) > 1 else ""

            if command == "WELCOME":
                p_parts = payload.split('|')
                self.my_player_id = int(p_parts[0])
                self.my_color = p_parts[1]
                self.grid_size = int(p_parts[2])
                self.root.title(f"Deny & Conquer Client - {self.player_name} (ID: {self.my_player_id})")
                self.log_message(f"Connected successfully! Your color is {self.my_color}")
                self.create_game_widgets()
                self.calculate_square_size()
                self.draw_grid()
                self.board = [[0] * self.grid_size for _ in range(self.grid_size)]

            elif command == "UPDATE_BOARD":
                new_board = ast.literal_eval(payload)
                self.board = new_board
                self.update_board_display()

            elif command == "UPDATE_PLAYERS":
                self.players = ast.literal_eval(payload)
                self.update_players_display()

            elif command == "UPDATE_SCORES":
                self.scores = ast.literal_eval(payload)
                self.update_scores_display()

            elif command == "LOCK_GRANTED":
                r, c = map(int, payload.split('|'))
                if self.pending_lock_request == (r, c):
                    print(f"Lock granted for my request at ({r},{c})")
                    self.is_scribbling = True
                    self.scribble_square = (r, c)
                    self.scribble_pixels.clear()
                    self.clear_scribble_lines()
                    self.draw_lock_indicator(r, c, self.my_player_id)
                    self.status_label.config(text=f"Scribbling in square ({r},{c})... Release mouse to claim.")
                else:
                    print(f"WARN: Received LOCK_GRANTED for ({r},{c}), but wasn't expecting it for this square ({self.pending_lock_request}).")
                self.pending_lock_request = None

            elif command == "LOCK_DENIED":
                r, c = map(int, payload.split('|'))
                if self.pending_lock_request == (r, c):
                    self.status_label.config(text=f"Could not lock square ({r},{c}). It's busy or already taken.")
                    self.log_message(f"Lock denied for square ({r},{c}).")
                    self.pending_lock_request = None

            elif command == "SQUARE_LOCKED":
                r, c, player_id = map(int, payload.split('|'))
                self.locked_squares[(r, c)] = player_id
                self.draw_lock_indicator(r, c, player_id)
                if self.pending_lock_request == (r, c) and player_id != self.my_player_id:
                    self.status_label.config(text=f"Square ({r},{c}) was just locked by Player {player_id}.")
                    self.pending_lock_request = None

            elif command == "SQUARE_UNLOCKED":
                r, c = map(int, payload.split('|'))
                if (r, c) in self.locked_squares:
                    del self.locked_squares[(r, c)]
                    self.remove_lock_indicator(r, c)
                if self.pending_lock_request == (r, c):
                    self.status_label.config(text=f"Square ({r},{c}) was unlocked before lock granted.")
                    self.pending_lock_request = None

            elif command == "INFO":
                self.log_message(f"Server Info: {payload}")
                self.status_label.config(text=payload)

            elif command == "ERROR":
                messagebox.showerror("Server Error", payload)
                self.log_message(f"Server Error: {payload}")

            elif command == "GAME_OVER":
                self.game_over = True
                self.is_scribbling = False
                self.status_label.config(text=f"GAME OVER! {payload}")
                messagebox.showinfo("Game Over", payload)
                self.log_message(f"--- {payload} ---")

            else:
                self.log_message(f"Unknown command from server: {command}")

        except Exception as e:
            self.log_message(f"Error processing message '{message}': {e}")
            import traceback
            traceback.print_exc()

    def handle_disconnection(self, reason):
        if self.connected:
            self.connected = False
            self.log_message(f"Disconnected: {reason}")
            messagebox.showinfo("Disconnected", f"Lost connection to the server.\nReason: {reason}")
            if self.status_label: self.status_label.config(text=f"Disconnected: {reason}")
            self.cleanup_connection()
            self.create_login_widgets()

    def cleanup_connection(self):
        self.connected = False
        if self.sock:
            try: self.sock.close()
            except Exception as e: print(f"Error closing socket: {e}")
            self.sock = None
        self.is_scribbling = False
        self.scribble_square = None
        self.scribble_pixels.clear()
        self.clear_scribble_lines()
        self.pending_lock_request = None

    def send_message(self, message):
        if self.connected and self.sock:
            try:
                print(f"Sending: {message.strip()}")
                self.sock.sendall(message.encode('utf-8'))
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                self.message_queue.put(("DISCONNECT", f"Error sending message: {e}"))
            except Exception as e:
                self.log_message(f"Unexpected error sending message: {e}")
        elif not self.game_over:
            self.log_message("Cannot send message: Not connected.")

    def calculate_square_size(self):
        if self.canvas and self.grid_size > 0:
            canvas_width = self.canvas.winfo_width()
            if canvas_width <= 1: canvas_width = int(self.canvas.cget("width"))
            self.square_pixel_size = canvas_width / self.grid_size
            self.total_pixels_in_square = self.square_pixel_size ** 2
            print(f"Canvas width: {canvas_width}, Grid: {self.grid_size}, Square Size: {self.square_pixel_size:.2f}, Total Pixels: {self.total_pixels_in_square:.2f}")

    def draw_grid(self):
        if not self.canvas: return
        self.canvas.delete("grid_line")
        self.calculate_square_size()
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width <= 1 : width = int(self.canvas.cget("width"))
        if height <= 1 : height = int(self.canvas.cget("height"))

        for i in range(1, self.grid_size):
            x = i * self.square_pixel_size
            self.canvas.create_line(x, 0, x, height, tag="grid_line", fill="lightgrey")
            y = i * self.square_pixel_size
            self.canvas.create_line(0, y, width, y, tag="grid_line", fill="lightgrey")

    def update_board_display(self):
        if not self.canvas or not self.board: return
        self.calculate_square_size()

        for r in range(self.grid_size):
            for c in range(self.grid_size):
                player_id = self.board[r][c]
                x0, y0, x1, y1 = self.grid_to_canvas_coords(r, c)

                fill_color = 'white'
                if player_id != 0 and player_id in self.players:
                    fill_color = self.players[player_id]['color']
                elif player_id !=0:
                    fill_color = 'grey'

                if (r, c) in self.canvas_squares:
                    try:
                        self.canvas.itemconfig(self.canvas_squares[(r, c)], fill=fill_color, outline='black')
                    except tk.TclError:
                        del self.canvas_squares[(r, c)]
                        item_id = self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill_color, outline='black', tags=("square", f"sq_{r}_{c}"))
                        self.canvas_squares[(r, c)] = item_id
                else:
                    item_id = self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill_color, outline='black', tags=("square", f"sq_{r}_{c}"))
                    self.canvas_squares[(r, c)] = item_id
                self.canvas.tag_raise("grid_line")
                self.canvas.tag_raise("lock_indicator")

    def update_players_display(self):
        if not self.players_scores_label: return
        text = ""
        sorted_player_ids = sorted(self.players.keys())

        for p_id in sorted_player_ids:
            player = self.players.get(p_id)
            if player:
                score = self.scores.get(p_id, 0)
                you_marker = " (You)" if p_id == self.my_player_id else ""
                text += f"{player['name']}{you_marker} [{player['color']}] Score: {score}\n"

        if not text: text = "No players yet."
        self.players_scores_label.config(text=text)

    def update_scores_display(self):
        self.update_players_display()

    def draw_lock_indicator(self, r, c, player_id):
        if not self.canvas: return
        self.remove_lock_indicator(r, c)
        x0, y0, x1, y1 = self.grid_to_canvas_coords(r, c)
        mid_x, mid_y = (x0 + x1) / 2, (y0 + y1) / 2

        indicator_color = LOCK_INDICATOR_COLOR_OTHER
        text_color = 'black'
        if player_id == self.my_player_id:
            indicator_color = LOCK_INDICATOR_COLOR_SELF
            text_color = 'white'

        locking_player_name = self.players.get(player_id, {}).get('name', f'P{player_id}')
        item_id = self.canvas.create_text(mid_x, mid_y, text=f"{locking_player_name}",
                                          fill=text_color, justify=tk.CENTER, state=tk.DISABLED,
                                          tags=("lock_indicator", f"lock_{r}_{c}"))

        self.lock_indicators[(r, c)] = item_id
        self.canvas.tag_raise(item_id)

    def remove_lock_indicator(self, r, c):
        if not self.canvas: return
        if (r, c) in self.lock_indicators:
            try:
                self.canvas.delete(self.lock_indicators[(r, c)])
            except tk.TclError:
                pass
            del self.lock_indicators[(r, c)]

    def coords_to_grid(self, x, y):
        if not self.canvas or self.square_pixel_size <= 0: return None, None
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        if canvas_width <=1: canvas_width = int(self.canvas.cget("width"))
        if canvas_height <=1: canvas_height = int(self.canvas.cget("height"))

        x = max(0, min(x, canvas_width - 1))
        y = max(0, min(y, canvas_height - 1))

        col = int(x // self.square_pixel_size)
        row = int(y // self.square_pixel_size)
        col = max(0, min(col, self.grid_size - 1))
        row = max(0, min(row, self.grid_size - 1))
        return row, col

    def grid_to_canvas_coords(self, r, c):
        x0 = c * self.square_pixel_size
        y0 = r * self.square_pixel_size
        x1 = x0 + self.square_pixel_size
        y1 = y0 + self.square_pixel_size
        return x0, y0, x1, y1

    def on_canvas_press(self, event):
        if self.game_over or not self.connected: return
        if self.is_scribbling: return

        r, c = self.coords_to_grid(event.x, event.y)
        if r is None: return

        print(f"Clicked on grid ({r},{c})")

        is_white = self.board[r][c] == 0
        is_locked = (r, c) in self.locked_squares

        if is_white and not is_locked:
            self.status_label.config(text=f"Requesting lock for square ({r},{c})...")
            self.pending_lock_request = (r, c)
            self.send_message(f"LOCK_REQUEST|{r}|{c}\n")
        elif not is_white:
            self.status_label.config(text=f"Square ({r},{c}) is already taken.")
        elif is_locked:
            locker_id = self.locked_squares.get((r,c))
            locker_name = self.players.get(locker_id, {}).get('name', f'Player {locker_id}')
            self.status_label.config(text=f"Square ({r},{c}) is currently locked by {locker_name}.")

    def on_canvas_drag(self, event):
        if self.game_over or not self.is_scribbling or self.scribble_square is None:
            return

        r_current, c_current = self.coords_to_grid(event.x, event.y)
        if (r_current, c_current) == self.scribble_square:
            x, y = event.x, event.y
            radius = 2
            line_id = self.canvas.create_oval(x-radius, y-radius, x+radius, y+radius,
                                               fill=SCRIBBLE_COLOR, outline='', tags="scribble")
            self.scribble_lines.append(line_id)

            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    self.scribble_pixels.add((int(x+dx), int(y+dy)))

    def clear_scribble_lines(self):
        if not self.canvas: return
        for item_id in self.scribble_lines:
            try: self.canvas.delete(item_id)
            except tk.TclError: pass
        self.scribble_lines.clear()

    def on_canvas_release(self, event):
        if self.game_over or not self.is_scribbling or self.scribble_square is None:
            if self.pending_lock_request:
                print("Mouse released while lock request was pending.")
                self.pending_lock_request = None
                self.status_label.config(text="Lock request cancelled.")
            return

        r, c = self.scribble_square
        print(f"Released mouse in square ({r},{c})")

        coverage = len(self.scribble_pixels) / self.total_pixels_in_square
        self.log_message(f"Square ({r},{c}): Scribbled {len(self.scribble_pixels)} 'pixels', Coverage ~{coverage:.2%}")

        if coverage >= TARGET_COVERAGE:
            self.log_message(f"Attempting to claim square ({r},{c}) - Coverage OK.")
            self.send_message(f"CLAIM_ATTEMPT|{r}|{c}\n")
            self.status_label.config(text=f"Attempting claim for ({r},{c})...")
        else:
            self.log_message(f"Releasing lock for square ({r},{c}) - Coverage < {TARGET_COVERAGE:.0%}.")
            self.send_message(f"RELEASE_LOCK|{r}|{c}\n")
            self.status_label.config(text=f"Claim failed for ({r},{c}) - not enough coverage.")

        self.is_scribbling = False
        self.scribble_square = None
        self.scribble_pixels.clear()
        self.clear_scribble_lines()

    def on_closing(self):
        print("Closing window...")
        if self.connected and self.sock:
            print("Sending disconnect message...")
            self.send_message("DISCONNECT\n")
            time.sleep(0.1)
        self.connected = False
        self.cleanup_connection()
        self.root.destroy()
        sys.exit(0)

if __name__ == "__main__":
    root = tk.Tk()
    app = GameClientApp(root)
    root.mainloop()
