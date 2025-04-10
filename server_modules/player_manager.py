import threading

PLAYER_COLORS = ['#FF0000', '#0000FF', '#00FF00', '#FFA500',
                 '#800080', '#FFFF00', '#00FFFF', '#FF00FF']

class PlayerManager:
    def __init__(self, max_players):
        self.max_players = max_players
        self.clients = {}  
        self.lock = threading.Lock()
        self.next_player_id = 1

    def handle_client(self, client_socket, addr, board, broadcaster, on_game_over):
        player_id, player_name, player_color = None, None, None

        try:
            with self.lock:
                if len(self.clients) >= self.max_players:
                    client_socket.sendall(b"ERROR|Server is full.\n")
                    return

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
                self.clients[client_socket] = {
                    'id': player_id,
                    'name': player_name,
                    'color': player_color
                }

            welcome_msg = f"WELCOME|{player_id}|{player_color}|{board.grid_size}\n"
            client_socket.sendall(welcome_msg.encode('utf-8'))
            broadcaster.broadcast_players()
            broadcaster.broadcast_board()
            broadcaster.broadcast_scores()
            broadcaster.broadcast(f"INFO|{player_name} joined the game.\n", sender_socket=client_socket, exclude_sender=True)

            buffer = ""
            while True:
                data = client_socket.recv(4096)
                if not data:
                    break

                buffer += data.decode('utf-8')
                while '\n' in buffer:
                    message, buffer = buffer.split('\n', 1)
                    self.process_message(message.strip(), client_socket, player_id, board, broadcaster, on_game_over)
        
        except Exception as e:
            print(f"Exception with {addr}: {e}")
        finally:
            self.disconnect(client_socket, board, broadcaster)

    def process_message(self, message, sock, player_id, board, broadcaster, on_game_over):
        parts = message.split('|')
        command = parts[0]

        if command == "LOCK_REQUEST" and len(parts) == 3:
            r, c = int(parts[1]), int(parts[2])
            granted = board.try_lock(r, c, player_id)
            if granted:
                sock.sendall(f"LOCK_GRANTED|{r}|{c}\n".encode())
                broadcaster.broadcast_lock(r, c, player_id)
            else:
                sock.sendall(f"LOCK_DENIED|{r}|{c}\n".encode())

        elif command == "CLAIM_ATTEMPT" and len(parts) == 3:
            r, c = int(parts[1]), int(parts[2])
            success = board.claim(r, c, player_id)
            if success:
                broadcaster.broadcast_board()
                broadcaster.broadcast_scores()
                on_game_over()

        elif command == "RELEASE_LOCK" and len(parts) == 3:
            r, c = int(parts[1]), int(parts[2])
            board.release_lock(r, c, player_id)
            broadcaster.broadcast_unlock(r, c)

        elif command == "DISCONNECT":
            self.disconnect(sock, board, broadcaster)

    def disconnect(self, sock, board, broadcaster):
        with self.lock:
            if sock in self.clients:
                info = self.clients.pop(sock)
                print(f"Player {info['name']} (ID: {info['id']}) disconnected.")
                board.release_all_locks(info['id'])
                broadcaster.broadcast(f"INFO|{info['name']} left the game.\n")
                broadcaster.broadcast_players()
                broadcaster.broadcast_scores()
            try:
                sock.close()
            except:
                pass

    def get_players(self):
        with self.lock:
            return {
                info['id']: {'name': info['name'], 'color': info['color']}
                for info in self.clients.values()
            }

    def disconnect_all(self):
        with self.lock:
            for sock in list(self.clients):
                self.disconnect(sock, None, None)
            self.clients.clear()
