# CMPT 371: Deny & Conquer

Deny & Conquer is a multiplayer grid-based game where players compete to claim squares on a shared game board. The game is implemented using Python and leverages the `pygame` library for the client-side interface and socket programming for server-client communication.

## Features
- **Multiplayer Gameplay**: Supports multiple players competing in real-time.
- **Grid-based Board**: Players can lock and claim squares on a shared grid.
- **Dynamic Updates**: Real-time updates of the board, player scores, and game state.
- **Server-Client Architecture**: A dedicated server manages the game state and broadcasts updates to all connected clients.

## Requirements
- Python 3.8 or higher and pip

## Installation
1. Install Python 3.8 or higher from the [official website](https://www.python.org/downloads/).

2. Install the `pygame` library using pip 
   ```sh
   pip install -r requirements.txt
   ```
3. Start the server:
   ```sh
   python server.py
   ```
4. Start the client:
   ```sh
   python client.py
   ```
5. Connect to the server using the client interface.

## Usage

- Players can join the game by entering their username and connecting to the server.
- Once connected, players can see the game board and their current score.
- Players can click on squares to lock them, claiming them for their score.
- Players scribble on the board to indicate their claimed squares.
- The game ends when all squares are claimed or a predefined time limit is reached.
- The player with the highest score at the end of the game wins.

