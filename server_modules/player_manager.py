import threading

# List of player colors to choose from
PLAYER_COLORS = ['#FF0000', '#0000FF', '#00FF00', '#FFA500',
                 '#800080', '#FFFF00', '#00FFFF', '#FF00FF']

class PlayerManager:
    """PlayerManager class manages the connected players. 
        It handles client connections, disconnections, and message processing."""
    def __init__(self, max_players):
        """Initialize the PlayerManager instance with given max_players."""
        self.max_players = max_players
        self.clients = {}  
        self.lock = threading.Lock()
        self.next_player_id = 1

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
                self.clients[client_socket] = {
                    'id': player_id,
                    'name': player_name,
                    'color': player_color
                }

            welcome_msg = f"WELCOME|{player_id}|{player_color}|{board.grid_size}\n"
            client_socket.sendall(welcome_msg.encode('utf-8'))
            # Broadcast the current state of the board
            broadcaster.broadcast_players()
            broadcaster.broadcast_board()
            broadcaster.broadcast_scores()
            broadcaster.broadcast(f"INFO|{player_name} joined the game.\n", sender_socket=client_socket, exclude_sender=True)

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

    def process_message(self, message, sock, player_id, board, broadcaster, on_game_over):
        """Process a message from a client."""
        # Split the incoming message into parts based on the '|' delimiter
        parts = message.split('|')
        command = parts[0]

        # Handle a LOCK_REQUEST command
        if command == "LOCK_REQUEST" and len(parts) == 3:
            r, c = int(parts[1]), int(parts[2]) 
            # Attempt to lock the specified cell for the player
            granted = board.try_lock(r, c, player_id)
            if granted:
                # Notify the client that the lock was granted
                sock.sendall(f"LOCK_GRANTED|{r}|{c}\n".encode())
                # Broadcast the lock to all other clients
                broadcaster.broadcast_lock(r, c, player_id)
            else:
                # Notify the client that the lock was denied
                sock.sendall(f"LOCK_DENIED|{r}|{c}\n".encode())

        # Handle a CLAIM_ATTEMPT command
        elif command == "CLAIM_ATTEMPT" and len(parts) == 3:
            r, c = int(parts[1]), int(parts[2])  
            # Attempt to claim the specified cell for the player
            success = board.claim(r, c, player_id)
            if success:
                # Broadcast the updated board and scores to all clients
                broadcaster.broadcast_board()
                broadcaster.broadcast_scores()
                # Check if the game is over and handle it if necessary
                on_game_over()

        # Handle a RELEASE_LOCK command
        elif command == "RELEASE_LOCK" and len(parts) == 3:
            r, c = int(parts[1]), int(parts[2])  
            # Release the lock on the specified cell for the player
            board.release_lock(r, c, player_id)
            # Broadcast the unlock to all other clients
            broadcaster.broadcast_unlock(r, c)

        # Handle a DISCONNECT command
        elif command == "DISCONNECT":
            # Disconnect the client and clean up resources
            self.disconnect(sock, board, broadcaster)

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
                # Broadcast the updated state of the scores to all connected clients
                broadcaster.broadcast_scores()
        try:
            sock.close()
        except:
            pass

    def get_players(self):
        """Get a dictionary of all connected players."""
        with self.lock:
            return {
                info['id']: {'name': info['name'], 'color': info['color']}
                for info in self.clients.values()
            }

    def disconnect_all(self):
        """Disconnect all clients."""
        with self.lock:
            for sock in list(self.clients):
                self.disconnect(sock, None, None)
            self.clients.clear()

