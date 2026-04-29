from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import json

app = FastAPI()

class Game:
    def __init__(self):
        self.board = [""] * 9
        self.current_turn = "X"
        self.winner = None
        self.players = []

    def make_move(self, player, index):
        if self.board[index] == "" and player == self.current_turn and not self.winner:
            self.board[index] = player
            if self.check_win(player):
                self.winner = player
            else:
                self.current_turn = "O" if self.current_turn == "X" else "X"
            return True
        return False

    def check_win(self, player):
        wins = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
        for a, b, c in wins:
            if self.board[a] == self.board[b] == self.board[c] == player:
                return True
        return False

game = Game()

@app.websocket("/ws/{player_id}")
async def websocket_endpoint(websocket: WebSocket, player_id: str):
    await websocket.accept()
    game.players.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            move = json.loads(data)
            index = move.get("index")
            if game.make_move(player_id, index):
                state = {
                    "board": game.board,
                    "current_turn": game.current_turn,
                    "winner": game.winner
                }
                for player in game.players:
                    await player.send_json(state)
    except WebSocketDisconnect:
        game.players.remove(websocket)

app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")