import socket
import tkinter as tk
import time
import json

HOST = '127.0.0.1'
PORT = 53333

class SudokuClient:
    def __init__(self):
        self.grid = [[None for _ in range(9)] for _ in range(9)]
        self.window = tk.Tk()
        self.window.title("MultiDoku")
        self.socket = None
        self.connected = False
        self.create_grid()
        
    def create_grid(self):
        for i in range(9):
            for j in range(9):
                var = tk.StringVar()
                cell = tk.Entry(self.window, width=2, font=("Arial", 18), justify="center", textvariable=var)
                cell.grid(row=i, column=j, padx=5, pady=5)
                var.trace("w", lambda name, index, mode, var=var, i=i, j=j: self.validate_input(var, i, j))
                self.grid[i][j] = {"entry": cell, "var": var}
    
    def validate_input(self, var, i, j):
        value = var.get()
        # Send empty cell to server if value is deleted
        if value == "":
            self.send_move_to_server(i, j, "")
            return
        
        if not (len(value) == 1 and value.isdigit() and "1" <= value <= "9"):
            last_char = value[-1] if value else ""
            if len(last_char) == 1 and last_char.isdigit() and "1" <= last_char <= "9":
                var.set(last_char)
                # Send valid input to server
                self.send_move_to_server(i, j, last_char)
            else:
                var.set("")
        else:
            # Already valid single digit
            self.send_move_to_server(i, j, value)
    
    def send_move_to_server(self, row, col, value):
            
        message = {
            "type": "move",
            "cell": [row, col],
            "value": value
        }
        
        try:
            # Convert the message to JSON and send it
            json_message = json.dumps(message)
            self.socket.sendall((json_message + "\n").encode())
            print(f"Sent move to server: {json_message}")
        except Exception as e:
            print(f"Error sending move to server: {e}")
            
    def connect_to_server(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((HOST, PORT))
            self.connected = True
            print("Connected to server")
            #handle more comminucation to the server
        except Exception as e:
            print(f"Failed to connect to server: {e}")
    
    def start(self):
        self.connect_to_server()
        self.window.mainloop()
if __name__=="__main__":
    client = SudokuClient()
    client.start()