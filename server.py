import socket
import threading
import time
import json
from random import sample

HOST = '127.0.0.1'
PORT = 53333

class Cell:
    def __init__(self):
        self.cell = None # [row, column] of the cell
        
        self.value = None # Value of the cell
        self.lock = threading.Lock() #Object locking mechanism
        self.owner = None # ID of the player who owns the cell
        self.socket = None

        
class SudokuServer:
    def __init__(self):
        self.grid=[[Cell() for _ in range(9)]  for _ in range(9)]
        self.game_started = False
        self.players = {}
        self.threads = []
        
    def client_join(self, conn, addr, player_id):
        for i in self.players:
            self.players[i].sendall(f"Player {player_id} joined the game.".encode())
            buffer = ""
            while True:
                try:
                    data = conn.recv(1024).decode()
                    if not data:
                        print(f"Player {player_id} disconnected.")
                        break
                    
                    buffer += data
                    
                    # Process messages in the buffer one by one
                    while "\n" in buffer:
                        message, buffer = buffer.split("\n", 1)
                        # Print out the JSON in the server, process later
                        try:
                            json_data = json.loads(message)
                            print(f"Received from player {player_id}: {json_data}")
                            
                        except json.JSONDecodeError:
                            print(f"Received invalid JSON: {message}")
                    
                except ConnectionResetError:
                    print(f"Connection with player {player_id} lost.")
                    break
                except Exception as e:
                    print(f"Error: {e}")
                    break
        
    def create_board(self):
        base = 3
        side  = base*base

        # pattern for a baseline valid solution
        def pattern(r,c): return (base*(r%base)+r//base+c)%side

        # randomize rows, columns and numbers (of valid base pattern)
        def shuffle(s): return sample(s,len(s)) 
        rBase = range(base) 
        rows  = [ g*base + r for g in shuffle(rBase) for r in shuffle(rBase) ] 
        cols  = [ g*base + c for g in shuffle(rBase) for c in shuffle(rBase) ]
        nums  = shuffle(range(1,base*base+1))

        # produce board using randomized baseline pattern
        completed_board = [ [nums[pattern(r,c)] for c in cols] for r in rows ]

        empty_board=completed_board
        
        squares = side*side
        empties = squares * 3//4
        for p in sample(range(squares),empties):
            empty_board[p//side][p%side] = 0
        
        for line in empty_board: print(line)
        
        return completed_board, empty_board
    
    #Thread function that listens for all gameplay messages that a client sends.
    #Broadcasts any incoming messages from a client to all other clients
    def gameplay(self, completed_board, empty_board):
        return
        #logic needs work: we want to broadcast to every player except the one that sends the message.
        #example:
        #   if player 1 makes a move, player 1 client sends message to server, server forwards it to all other players,
        #   they recieve the message: player 1 entered a 9 correctly! 
        
        #to broadcast to every player:
        # for i in self.players:
        #     self.players[i].sendall(message)
        
        #check if current board = completed board
        #   if true, then the game is completed, send a message to all clients that the game is over and show the winner.
        
        
        
    #Listens for a Connection, sends a board out to the client that joins, 
    #if client presses start game button, then no other clients can join, the game is started
    def start(self):
        print(f"Server started at {HOST}:{PORT}")
        #create a sudoku board
        print(f"Creating a new sudoku board...")
        completed_board, empty_board = server.create_board()
        #initialize a socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        with self.socket as s:
            #binds and listens for any connections to the server
            s.bind((HOST, PORT))
            s.listen(6) #Limits the number of players to 6
            player_id = 1 #Starts incrementing and assigning player IDs as they join

            #while the game has not started yet (all players have not joined)
            while True: 
                conn, addr = s.accept()
                print(f"Connected to {addr}")
                #starts a thread that displays connection messsage to all clients 
                threading.Thread(target=self.client_join, args=(conn, addr, player_id)).start()
                self.players[player_id]=conn
                
                
                board_json = json.dumps({"type": "empty_board", "board": empty_board})
                conn.sendall((board_json).encode())
                print(f"Sent Starting board to client {player_id}: {empty_board}")
                
                player_id += 1
                if(player_id==7):
                    self.game_started=True
                    break
            
                data = conn.recv(1024).decode()
                
                if(data=="start_game"):
                    self.game_started=True
                    break
                    
        for i in range(len(self.players)):
            self.threads[i] = threading.Thread(target=self.gameplay)
            self.threads[i].start()
                
        
    

if __name__ == "__main__":
    server = SudokuServer()

    server.start()
    #create an array of threads for each player, 
    #player thread will continue running and listen for any game updates
    
    #c1 = threading.Thread(target=server.start(), name='start')
    # c1.start()
    
    
            



