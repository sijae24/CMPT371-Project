import socket
import threading
import time

HOST = '127.0.0.1'
PORT = 53333

class Cell:
    def __init__(self):
        self.value = None #Value of the cell
        self.lock = threading.Lock() #Object locking mechanism
        self.owner = None #ID of the player who owns the cell
        
        
class SudokuServer:
    def __init__(self):
        self.grid=[[Cell() for _ in range(9)]  for _ in range(9)]
        self.players = {}
        self.lock = threading.Lock()
        
    def client_join(self, conn, addr, player_id):
        conn.sendall(f"Player {player_id} joined the game.".encode())
        while True:
            try:
                data = conn.recv(1024).decode()
                if not data:
                    print(f"Player {player_id} disconnected.")
                    break
            # Handle player actions (e.g., selecting a cell, entering a number)
            # Broadcast updates to all players
            except ConnectionResetError:
                print(f"Connection with {player_id} lost.")
                break
        conn.close()
        
    def start(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((HOST, PORT))
            s.listen(6) #Limits the number of players to 6
            print(f"Server started at {HOST}:{PORT}")
            player_id = 1 #Starts incrementing and assigning player IDs as they join
            while True:
                conn, addr = s.accept()
                print(f"Connected to {addr}")
                threading.Thread(target=self.client_join, args=(conn, addr, player_id)).start()
                player_id += 1

if __name__ == "__main__":
    server = SudokuServer()
    server.start()
            


