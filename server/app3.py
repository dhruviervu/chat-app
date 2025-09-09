# server/app.py
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

app = FastAPI()
connections = {}  # username -> websocket

@app.websocket("/ws/{username}")
async def ws_endpoint(ws: WebSocket, username: str):
    await ws.accept()
    connections[username] = ws
    print(f"{username} connected")

    try:
        while True:
            data = await ws.receive_text()
            payload = json.loads(data)
            recipient = payload.get("recipient")

            # Forward to recipient if online
            if recipient in connections:
                await connections[recipient].send_text(data)

            # Optionally: also forward back to sender (if you want server ACK)
            # await ws.send_text(data)

    except WebSocketDisconnect:
        print(f"{username} disconnected")
        if username in connections:
            del connections[username]

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=8765,
        ssl_certfile="certs/server.crt",
        ssl_keyfile="certs/server.key",
    )
