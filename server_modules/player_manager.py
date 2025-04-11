import threading
import time

# List of player colors to choose from
PLAYER_COLORS = ['#FF0000', '#0000FF', '#00FF00', '#FFA500', '#800080', '#FFFF00', '#00FFFF', '#FF00FF']


class PlayerManager:
    """PlayerManager class manages the connected players.
    It handles client connections, disconnections, and message processing."""

    def __init__(self, max_players):
        """Initialize the PlayerManager instance with given max_players."""
        self.max_players = max_players
        self.clients = {}
        self.lock = threading.Lock()
        self.next_player_id = 1
        self.game_server = None  # Reference to game server for timer control

    def set_game_server(self, game_server):
        """Set reference to game server instance."""
        self.game_server = game_server

    def handle_client(self, client_socket, addr, board, broadcaster, on_game_over):
        """Handle a new client connection."""
        player_id, player_name, player_color = None, None, None

        try:
            # Check if the server is full
            with self.lock:
                if len(self.clients) >= self.max_players:
                    client_socket.sendall(b"ERROR|Server is full.\n")
                    return

                # Assign a player ID and color
                player_id = self.next_player_id
                self.next_player_id += 1
                player_color = PLAYER_COLORS[(player_id - 1) % len(PLAYER_COLORS)]

            # Wait for CONNECT message
            data = client_socket.recv(4096).decode('utf-8').strip()
            if not data.startswith("CONNECT|"):
                client_socket.sendall(b"ERROR|Invalid connection message.\n")
                return

            player_name = data.split('|', 1)[1].strip() or f"Player_{player_id}"

            with self.lock:
                # Add the player to the clients dictionary
                self.clients[client_socket] = {'id': player_id, 'name': player_name, 'color': player_color}

            welcome_msg = f"WELCOME|{player_id}|{player_color}|{board.grid_size}\n"
            client_socket.sendall(welcome_msg.encode('utf-8'))
            # Broadcast the current state of the board
            broadcaster.broadcast_players()
            broadcaster.broadcast_board()
            broadcaster.broadcast(
                f"INFO|{player_name} joined the game.\n", sender_socket=client_socket, exclude_sender=True
            )

            # Receive and process messages
            buffer = ""
            while True:
                # Receive a message
                data = client_socket.recv(4096)
                if not data:
                    break

                # Process the message
                buffer += data.decode('utf-8')
                while '\n' in buffer:
                    message, buffer = buffer.split('\n', 1)
                    self.process_message(message.strip(), client_socket, player_id, board, broadcaster, on_game_over)
        
        except Exception as e:
            print(f"Exception with {addr}: {e}")
        finally:
            self.disconnect(client_socket, board, broadcaster)

    
    def process_message(self, message, client_socket, player_id, board, broadcaster, on_game_over):
        """Process a message from a client."""
        try:
            parts = message.split('|', 1)
            command = parts[0]
            payload = parts[1] if len(parts) > 1 else ""
    
            # Handle a CLAIM_ATTEMPT command
            if command == "CLAIM_ATTEMPT":
                r, c = map(int, payload.split('|'))
                # Attempt to claim the specified cell for the player
                success = board.claim(r, c, player_id)
                if success:
                    # Broadcast the updated board and scores to all clients
                    broadcaster.broadcast_board()
                    broadcaster.broadcast_scores()
                    # Check if the game is over and handle it if necessary
                    on_game_over()
    
            # Handle a SCRIBBLE_UPDATE command
            elif command == "SCRIBBLE_UPDATE":
                # Format: SCRIBBLE_UPDATE|row|col|x|y
                try:
                    parts = payload.split('|')
                    if len(parts) >= 3:
                        r, c = int(parts[0]), int(parts[1])
                        x, y = int(parts[2]), int(parts[3])
                        
                        # Check if the player has a lock on this square
                        if (r, c) in board.locks and board.locks[(r, c)] == player_id:
                            # Broadcast the scribble update to all clients
                            # Remove the exclude_socket parameter
                            broadcaster.broadcast(f"PLAYER_SCRIBBLE|{r}|{c}|{player_id}|{x}|{y}\n")
                            # Don't log every scribble update
                        else:
                            client_socket.sendall(f"ERROR|You don't have a lock on square ({r},{c}).\n".encode('utf-8'))
                except Exception as e:
                    print(f"Error processing SCRIBBLE_UPDATE: {e}")
                    client_socket.sendall(f"ERROR|Invalid scribble format: {e}\n".encode('utf-8'))
                
            # Handle a RELEASE_LOCK command
            elif command == "RELEASE_LOCK":
                r, c = map(int, payload.split('|'))
                # Release the lock on the specified cell for the player
                board.release_lock(r, c, player_id)
                # Broadcast the unlock to all other clients
                broadcaster.broadcast_unlock(r, c)
    
            # Handle a DISCONNECT command
            elif command == "DISCONNECT":
                # Disconnect the client and clean up resources
                self.disconnect(client_socket, board, broadcaster)
    
            # Keep this LOCK_REQUEST handler which has the correct format
            elif command == "LOCK_REQUEST":
                try:
                    # Add debug print to see what's coming in
                    print(f"LOCK_REQUEST payload: '{payload}'")
                    
                    # Split the payload and handle potential empty parts
                    parts = payload.split('|')
                    if len(parts) >= 2:
                        r, c = int(parts[0]), int(parts[1])
                    else:
                        # Try direct parsing if there's only one part (might be comma-separated)
                        if ',' in payload:
                            r, c = map(int, payload.split(','))
                        else:
                            # Try parsing as a single value
                            parts = payload.strip()
                            r, c = int(parts.split()[0]), int(parts.split()[1])
                    
                    print(f"Player {player_id} requesting lock for ({r},{c})")
                    
                    # Start timer on first lock request if not already started
                    if self.game_server and not self.game_server.timer_started:
                        self.game_server.timer_start_time = time.time()
                        self.game_server.timer_started = True
                        print("Game timer started!")
                    
                    # Check if the square is available (not claimed and not locked)
                    if board.is_square_available(r, c):
                        # Lock the square for this player
                        board.lock_square(r, c, player_id)
                        
                        # Send confirmation to the requesting client
                        client_socket.sendall(f"LOCK_GRANTED|{r}|{c}\n".encode('utf-8'))
                        
                        # Broadcast to all clients that the square is locked
                        broadcaster.broadcast(f"SQUARE_LOCKED|{r}|{c}|{player_id}\n")
                        print(f"Lock granted to player {player_id} for ({r},{c})")
                    else:
                        # Square is not available
                        client_socket.sendall(f"LOCK_DENIED|{r}|{c}\n".encode('utf-8'))
                        print(f"Lock denied to player {player_id} for ({r},{c})")
                except Exception as e:
                    print(f"Error processing LOCK_REQUEST: {e}, payload: '{payload}'")
                    client_socket.sendall(f"ERROR|Invalid lock request format: {e}\n".encode('utf-8'))
    
        except Exception as e:
            print(f"Error processing message '{message}' from player {player_id}: {e}")
            client_socket.sendall(f"ERROR|Invalid message format: {e}\n".encode('utf-8'))

    def disconnect(self, sock, board, broadcaster):
        """Disconnect a client."""
        with self.lock:
            # Check if the socket is actually in the dictionary of connected clients
            if sock in self.clients:
                # Get the information about the client that we're disconnecting
                info = self.clients.pop(sock)
                print(f"Player {info['name']} (ID: {info['id']}) disconnected.")
                # Release all of the locks that the player held
                board.release_all_locks(info['id'])
                # Broadcast a message to all connected clients about the disconnect
                broadcaster.broadcast(f"INFO|{info['name']} left the game.\n")
                # Broadcast the updated state of the players to all connected clients
                broadcaster.broadcast_players()
        try:
            sock.close()
        except:
            pass

    def get_players(self):
        """Get a dictionary of all connected players."""
        with self.lock:
            return {info['id']: {'name': info['name'], 'color': info['color']} for info in self.clients.values()}

    def disconnect_all(self):
        """Disconnect all clients."""
        with self.lock:
            for sock in list(self.clients):
                self.disconnect(sock, None, None)
            self.clients.clear()
