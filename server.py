import socket
import threading
import time
import sys
from collections import defaultdict

HOST = '0.0.0.0' # Listen on all available network interfaces
PORT = 65433     # Different port than the previous example
BUFFER_SIZE = 4096 # Increased buffer for potentially larger board/player data
GRID_SIZE = 8
MAX_PLAYERS = 4
PLAYER_COLORS = ['#FF0000', '#0000FF', '#00FF00', '#FFA500',  # Red, Blue, Green, Orange
                 '#800080', '#FFFF00', '#00FFFF', '#FF00FF'] # Purple, Yellow, Cyan, Magenta

clients = {} # socket: {'name': str, 'id': int, 'color': str}
board = [[0] * GRID_SIZE for _ in range(GRID_SIZE)] # 0=white, player_id otherwise
locked_squares = {} # (row, col): player_id - Stores who is currently scribbling where
scores = defaultdict(int) # player_id: count
game_state_lock = threading.Lock()
next_player_id = 1
game_active = True # To stop accepting connections/commands when game over

# --- Broadcasting Functions ---

def broadcast(message, sender_socket=None, exclude_sender=False):
    """ Sends a message to all connected clients """
    encoded_message = message.encode('utf-8')
    print(f"Broadcasting: {message.strip()}") # Server console log

    # Iterate over a copy of the client sockets' keys
    current_clients = list(clients.keys())
    for client_socket in current_clients:
        if exclude_sender and client_socket == sender_socket:
            continue
        try:
            client_socket.sendall(encoded_message)
        except (BrokenPipeError, ConnectionResetError):
            print(f"Client {clients.get(client_socket, {}).get('name', 'Unknown')} disconnected abruptly during broadcast.")
            # Schedule disconnect handling outside the broadcast loop if needed,
            # but handle_client loop usually catches this anyway.
            # handle_disconnect(client_socket) # Careful about modifying list while iterating
        except Exception as e:
            print(f"Error broadcasting to client {clients.get(client_socket, {}).get('name', 'Unknown')}: {e}")
            # Maybe schedule disconnect here too

def broadcast_board():
    """ Broadcasts the current board state """
    with game_state_lock:
        board_repr = repr(board)
    broadcast(f"UPDATE_BOARD|{board_repr}\n")

def broadcast_players():
    """ Broadcasts the current player list and their info """
    with game_state_lock:
        # Create a serializable version of clients info {id: {'name': name, 'color': color}}
        players_info = {
            details['id']: {'name': details['name'], 'color': details['color']}
            for details in clients.values()
        }
        players_repr = repr(players_info)
    broadcast(f"UPDATE_PLAYERS|{players_repr}\n")

def broadcast_scores():
    """ Calculates scores from the board and broadcasts them """
    with game_state_lock:
        current_scores = defaultdict(int)
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                player_id = board[r][c]
                if player_id != 0:
                    current_scores[player_id] += 1
        scores.clear()
        scores.update(current_scores)
        scores_repr = repr(dict(scores)) # Convert defaultdict for cleaner repr
    broadcast(f"UPDATE_SCORES|{scores_repr}\n")

def broadcast_lock_update(r, c, player_id):
    """ Broadcasts that a square has been locked """
    broadcast(f"SQUARE_LOCKED|{r}|{c}|{player_id}\n")

def broadcast_unlock_update(r, c):
    """ Broadcasts that a square has been unlocked """
    broadcast(f"SQUARE_UNLOCKED|{r}|{c}\n")

# --- Game Logic ---

def check_game_over():
    """ Checks if all squares are filled and broadcasts result """
    global game_active
    with game_state_lock:
        if not game_active: # Already over
            return False

        filled_squares = 0
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                if board[r][c] != 0:
                    filled_squares += 1

        if filled_squares == GRID_SIZE * GRID_SIZE:
            game_active = False # Stop game logic
            winner_message = "Game Over! "
            max_score = 0
            winners = []

            # Recalculate final scores
            final_scores = defaultdict(int)
            for r in range(GRID_SIZE):
                for c in range(GRID_SIZE):
                    player_id = board[r][c]
                    if player_id != 0:
                        final_scores[player_id] += 1

            if not final_scores:
                 winner_message += "No squares claimed."
            else:
                max_score = max(final_scores.values())
                player_details = {
                    details['id']: details['name']
                    for details in clients.values()
                }

                for p_id, score in final_scores.items():
                    if score == max_score:
                        winners.append(player_details.get(p_id, f"Player {p_id}"))

                if len(winners) == 1:
                    winner_message += f"{winners[0]} wins with {max_score} squares!"
                else:
                    winner_message += f"It's a tie between {', '.join(winners)} with {max_score} squares!"

            print(winner_message)
            broadcast(f"GAME_OVER|{winner_message}\n")
            # Optionally: Kick all clients after a delay? Close server?
            return True
        return False

def handle_disconnect(client_socket):
    """ Handles client disconnection """
    player_id_to_remove = None
    player_name = "Unknown"
    with game_state_lock:
        if client_socket in clients:
            player_info = clients.pop(client_socket)
            player_id_to_remove = player_info['id']
            player_name = player_info['name']
            print(f"Player {player_name} (ID: {player_id_to_remove}) disconnected.")

            # Remove player's locks if any
            squares_to_unlock = []
            for (r, c), locking_player_id in list(locked_squares.items()): # Iterate copy
                if locking_player_id == player_id_to_remove:
                    squares_to_unlock.append((r,c))
            for r,c in squares_to_unlock:
                 del locked_squares[(r,c)]
                 # No need to set board[r][c]=0, it should already be 0 if locked
                 print(f"Auto-unlocked square ({r},{c}) held by disconnecting player {player_name}")
                 broadcast_unlock_update(r, c) # Inform others

            # Don't remove score immediately, let final calculation handle it
            # if player_id_to_remove in scores:
            #    del scores[player_id_to_remove]

        try:
            client_socket.close()
        except Exception as e:
            print(f"Error closing socket for {player_name}: {e}")

    if player_id_to_remove is not None:
        broadcast(f"INFO|{player_name} left the game.\n")
        broadcast_players() # Update player list for remaining players
        broadcast_scores()  # Scores might change if disconnected player had squares

# --- Client Handling Thread ---

def handle_client(client_socket, addr):
    """ Handles communication with a single client """
    global next_player_id
    player_id = None
    player_name = None
    player_color = None

    try:
        # --- Connection Phase ---
        with game_state_lock:
            if len(clients) >= MAX_PLAYERS:
                print(f"Connection refused from {addr}: Server full ({len(clients)}/{MAX_PLAYERS})")
                client_socket.sendall(b"ERROR|Server is full.\n")
                return
            if not game_active:
                 print(f"Connection refused from {addr}: Game already finished.")
                 client_socket.sendall(b"ERROR|Game has already finished.\n")
                 return

            # Assign Player ID and Color
            player_id = next_player_id
            next_player_id += 1
            color_index = (player_id - 1) % len(PLAYER_COLORS)
            player_color = PLAYER_COLORS[color_index]

        # First message must be CONNECT|name
        data = client_socket.recv(BUFFER_SIZE).decode('utf-8').strip()
        if data.startswith("CONNECT|"):
            player_name = data.split('|', 1)[1].strip()
            if not player_name: player_name = f"Player_{player_id}" # Default name

            # Add client to list (needs lock)
            with game_state_lock:
                clients[client_socket] = {'name': player_name, 'id': player_id, 'color': player_color}
                # Initialize score if not present (though calculated from board mainly)
                if player_id not in scores: scores[player_id] = 0

            print(f"Player {player_name} (ID: {player_id}, Color: {player_color}) connected from {addr}")
            welcome_msg = f"WELCOME|{player_id}|{player_color}|{GRID_SIZE}\n"
            client_socket.sendall(welcome_msg.encode('utf-8'))

            # Send current state to the new player and update others
            broadcast_players()
            broadcast_board() # Send initial board
            broadcast_scores()
            broadcast(f"INFO|{player_name} joined the game.\n", sender_socket=client_socket, exclude_sender=True)

        else:
            print(f"Invalid first message from {addr}: {data}")
            client_socket.sendall(b"ERROR|Invalid connection sequence. Send CONNECT|name.\n")
            return # Disconnects by ending the thread

        # --- Main Message Loop ---
        buffer = ""
        while True:
             # Read data chunk
            try:
                data = client_socket.recv(BUFFER_SIZE)
                if not data:
                    print(f"Client {player_name} closed connection (empty data).")
                    break # Disconnect

                buffer += data.decode('utf-8')

                # Process complete messages (newline terminated)
                while '\n' in buffer:
                    message, buffer = buffer.split('\n', 1)
                    message = message.strip()
                    if not message: continue # Skip empty lines

                    print(f"Received from {player_name}: {message}")
                    if not game_active:
                        print("Ignoring command, game over.")
                        continue # Ignore commands after game over

                    parts = message.split('|')
                    command = parts[0]

                    # --- Handle Commands ---
                    if command == "LOCK_REQUEST" and len(parts) == 3:
                        try:
                            r, c = int(parts[1]), int(parts[2])
                            granted = False
                            with game_state_lock:
                                if 0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE:
                                    if board[r][c] == 0 and (r, c) not in locked_squares:
                                        locked_squares[(r, c)] = player_id
                                        granted = True
                                    # Else: square not white or already locked
                                else:
                                     print(f"Invalid coords in LOCK_REQUEST from {player_name}: ({r},{c})")

                            if granted:
                                print(f"Lock granted to {player_name} for ({r},{c})")
                                client_socket.sendall(f"LOCK_GRANTED|{r}|{c}\n".encode('utf-8'))
                                broadcast_lock_update(r, c, player_id)
                            else:
                                print(f"Lock denied to {player_name} for ({r},{c})")
                                client_socket.sendall(f"LOCK_DENIED|{r}|{c}\n".encode('utf-8'))

                        except (ValueError, IndexError) as e:
                            print(f"Invalid LOCK_REQUEST format from {player_name}: {message} - {e}")
                            client_socket.sendall(b"ERROR|Invalid LOCK_REQUEST format.\n")

                    elif command == "CLAIM_ATTEMPT" and len(parts) == 3:
                        try:
                            r, c = int(parts[1]), int(parts[2])
                            claim_successful = False
                            with game_state_lock:
                                if locked_squares.get((r, c)) == player_id:
                                    if 0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE:
                                        board[r][c] = player_id # Claim the square
                                        del locked_squares[(r, c)] # Release lock
                                        claim_successful = True
                                    else:
                                        print(f"Invalid coords in CLAIM_ATTEMPT from {player_name}: ({r},{c})")
                                else:
                                    # Player didn't hold the lock or lock expired/removed
                                    print(f"Invalid CLAIM_ATTEMPT from {player_name} for ({r},{c}) - lock not held.")
                                    # Optional: Send specific error?

                            if claim_successful:
                                print(f"Square ({r},{c}) claimed by {player_name}")
                                broadcast_board() # Includes the unlock visually
                                broadcast_scores()
                                # Check game end after successful claim
                                check_game_over()

                        except (ValueError, IndexError) as e:
                            print(f"Invalid CLAIM_ATTEMPT format from {player_name}: {message} - {e}")
                            client_socket.sendall(b"ERROR|Invalid CLAIM_ATTEMPT format.\n")

                    elif command == "RELEASE_LOCK" and len(parts) == 3:
                        try:
                            r, c = int(parts[1]), int(parts[2])
                            lock_released = False
                            with game_state_lock:
                                if locked_squares.get((r, c)) == player_id:
                                    del locked_squares[(r, c)]
                                    # Board square remains 0 (white)
                                    lock_released = True
                                else:
                                     print(f"Invalid RELEASE_LOCK from {player_name} for ({r},{c}) - lock not held.")

                            if lock_released:
                                print(f"Lock on ({r},{c}) released by {player_name} (failed claim)")
                                broadcast_unlock_update(r, c) # Inform others to remove visual lock

                        except (ValueError, IndexError) as e:
                            print(f"Invalid RELEASE_LOCK format from {player_name}: {message} - {e}")
                            client_socket.sendall(b"ERROR|Invalid RELEASE_LOCK format.\n")

                    elif command == "DISCONNECT":
                         print(f"{player_name} sent DISCONNECT command.")
                         break # Exit loop to handle disconnect

                    else:
                        print(f"Unknown command from {player_name}: {message}")
                        client_socket.sendall(b"ERROR|Unknown command.\n")


            except (ConnectionResetError, BrokenPipeError):
                print(f"Connection lost abruptly with {player_name}.")
                break # Disconnect
            except Exception as e:
                print(f"Error receiving/processing data from {player_name}: {e}")
                import traceback
                traceback.print_exc()
                break # Disconnect

    except Exception as e:
        print(f"Error in handle_client connection phase for {addr}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Ensure disconnect cleanup happens
        print(f"Cleaning up connection for {addr} (Player: {player_name})")
        handle_disconnect(client_socket)

# --- Main Server Loop ---

def start_server():
    global game_active
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen()
        print(f"Deny & Conquer Server listening on {HOST}:{PORT}")
        print(f"Grid Size: {GRID_SIZE}x{GRID_SIZE}, Max Players: {MAX_PLAYERS}")

        while game_active: # Stop accepting if game over? Or allow observers? For now, stop.
            try:
                client_socket, addr = server_socket.accept()
                print(f"Accepted connection from {addr}")
                # Start a new thread for each client
                client_thread = threading.Thread(target=handle_client, args=(client_socket, addr), daemon=True)
                client_thread.start()
            except KeyboardInterrupt:
                print("\nCtrl+C detected. Shutting down server...")
                game_active = False # Signal threads to stop main loops if possible
                break
            except OSError as e:
                 if game_active: # Only print error if we weren't expecting shutdown
                     print(f"Error accepting connections: {e}")
                 break # Exit loop on socket error
            except Exception as e:
                print(f"Error accepting connections: {e}")
                time.sleep(1) # Avoid busy-looping on persistent accept errors

    except Exception as e:
        print(f"Failed to start server: {e}")
    finally:
        # Cleanup
        print("Shutting down server...")
        game_active = False # Ensure flag is set
        # Gracefully inform connected clients (optional, handle_disconnect does closing)
        # broadcast("INFO|Server is shutting down.\n")
        # time.sleep(0.5) # Allow messages to send

        with game_state_lock:
            current_clients = list(clients.keys()) # Get a copy

        print(f"Closing {len(current_clients)} client sockets...")
        for sock in current_clients:
             handle_disconnect(sock) # Use existing disconnect logic

        print("Closing server socket...")
        server_socket.close()
        print("Server shut down.")
        # Force exit if threads are stuck (daemon=True should help, but just in case)
        sys.exit(0)


if __name__ == "__main__":
    start_server()
