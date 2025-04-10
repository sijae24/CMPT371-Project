
from server_modules.game_server import GameServer

# Start the game server and listen for incoming connections.
if __name__ == "__main__":
    server = GameServer()
    server.start()
