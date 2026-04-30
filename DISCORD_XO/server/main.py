from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import json
import asyncio
from game import Game

app = FastAPI()

# Хранилище игр
games = {}
# Очередь (user_id, websocket)
waiting = []
# Соответствие user_id -> websocket
connections = {}
game_id_counter = 0

app.mount("/static", StaticFiles(directory="../static", html=True), name="static")

@app.websocket("/ws")
async def ws_handler(websocket: WebSocket):
    global game_id_counter
    await websocket.accept()
    data = await websocket.receive_json()
    user_id = data.get("user_id")
    if not user_id:
        await websocket.close()
        return

    connections[user_id] = websocket

    if waiting:
        opp_id, opp_ws = waiting.pop(0)
        game_id_counter += 1
        game = Game(opp_id, user_id, game_id_counter)
        games[game_id_counter] = game
        # Сообщаем обоим
        await opp_ws.send_json({
            "type": "start",
            "game_id": game_id_counter,
            "your_turn": True,
            "piece": game.piece_of[opp_id],
            "state": game.to_dict()
        })
        await websocket.send_json({
            "type": "start",
            "game_id": game_id_counter,
            "your_turn": False,
            "piece": game.piece_of[user_id],
            "state": game.to_dict()
        })
        # Запускаем обработчики
        asyncio.create_task(player_loop(opp_ws, opp_id, game_id_counter))
        asyncio.create_task(player_loop(websocket, user_id, game_id_counter))
    else:
        waiting.append((user_id, websocket))
        await websocket.send_json({"type": "waiting"})

async def player_loop(ws: WebSocket, user_id: int, game_id: int):
    try:
        while True:
            msg = await ws.receive_json()
            if "coord" not in msg:
                continue
            coord = msg["coord"]
            game = games.get(game_id)
            if not game:
                await ws.send_json({"type": "error", "message": "Игра не найдена"})
                continue
            try:
                game.place_piece(user_id, coord)
            except ValueError as e:
                await ws.send_json({"type": "error", "message": str(e)})
                continue
            # Отправляем обновление всем
            state = game.to_dict()
            for pid in game.players:
                if pid in connections:
                    await connections[pid].send_json({
                        "type": "update",
                        "state": state,
                        "last_move": {"player": user_id, "coord": coord}
                    })
            if game.winner:
                # Финальное сообщение
                for pid in game.players:
                    if pid in connections:
                        await connections[pid].send_json({
                            "type": "gameover",
                            "winner": game.winner,
                            "state": state
                        })
                asyncio.create_task(remove_game(game_id))
    except WebSocketDisconnect:
        # Игрок вышел
        game = games.get(game_id)
        if game:
            other = next(p for p in game.players if p != user_id)
            if other in connections:
                await connections[other].send_json({"type": "opponent_left"})
            games.pop(game_id, None)
            for p in game.players:
                connections.pop(p, None)

async def remove_game(gid):
    await asyncio.sleep(60)
    game = games.pop(gid, None)
    if game:
        for p in game.players:
            connections.pop(p, None)

# Для Railway health-check
@app.get("/")
async def root():
    return {"status": "ok"}