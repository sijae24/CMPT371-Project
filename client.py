import socket
import tkinter as tk
import time

HOST = '127.0.0.1'
PORT = 53333

class SudokuClient:
    def __init__(self):
        self.grid = [[None for _ in range(9)] for _ in range(9)]
        self.window = tk.Tk()
        self.window.title("MultiDoku")
        self.create_grid()
        
    def create_grid(self):
        for i in range(9):
            for j in range(9):
                cell = tk.Entry(self.window, width=2, font=("Arial", 18), justify="center")
                cell.grid(row=i, column=j, padx=5, pady=5)
                self.grid[i][j] = cell
    def connect_to_server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, PORT))
            print("Connected to server")
            #handle more comminucation to the server
    
    def start(self):
        self.connect_to_server()
        self.window.mainloop()
        
if __name__=="__main__":
    client = SudokuClient()
    client.start()