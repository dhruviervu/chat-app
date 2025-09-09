# server/app.py
import ssl
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Dict

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active: Dict[str, WebSocket] = {}

    async def connect(self, user: str, websocket: WebSocket):
        await websocket.accept()
        self.active[user] = websocket
        print(f"[server] {user} connected. Active: {list(self.active.keys())}")

    def disconnect(self, user: str):
        if user in self.active:
            try:
                del self.active[user]
            except KeyError:
                pass
        print(f"[server] {user} disconnected. Active: {list(self.active.keys())}")

    async def send_personal(self, user: str, message: str):
        ws = self.active.get(user)
        if ws:
            await ws.send_text(message)
        else:
            print(f"[server] send_personal: user {user} not connected")

    async def broadcast(self, message: str, exclude_user: str = None):
        for u, ws in list(self.active.items()):
            if u == exclude_user:
                continue
            try:
                await ws.send_text(message)
            except Exception as e:
                print(f"[server] broadcast error to {u}: {e}")

manager = ConnectionManager()

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    # Register connection
    await manager.connect(username, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            print(f"[server] Received from {username}: {data[:200]}")
            # try parse JSON
            try:
                payload = json.loads(data)
            except Exception:
                payload = None

            # If payload has a recipient, forward only to that recipient
            if payload and isinstance(payload, dict) and payload.get("recipient"):
                recipient = payload.get("recipient")
                # send to recipient (if connected)
                await manager.send_personal(recipient, data)
                # optional: also echo to sender as ack
                await manager.send_personal(username, data)
            else:
                # if payload invalid or no recipient, broadcast to everyone (except sender)
                await manager.broadcast(data, exclude_user=username)

    except WebSocketDisconnect:
        manager.disconnect(username)
    except Exception as e:
        print(f"[server] websocket exception for {username}: {e}")
        manager.disconnect(username)


if __name__ == "__main__":
    # --- RUNNING OPTIONS ---
    # TLS (if you have certs in server/certs/server.crt+server.key)
    try:
        uvicorn.run(
            "app:app",  # run from the 'server' folder
            host="0.0.0.0",
            port=8765,
            ssl_certfile="certs/server.crt",
            ssl_keyfile="certs/server.key",
            reload=True,
        )
    except Exception as e:
        print("[server] uvicorn TLS start failed:", e)
        print("[server] Trying non-TLS fallback (ws)...")
        # Non-TLS fallback
        uvicorn.run(
            "app:app",
            host="0.0.0.0",
            port=8765,
            reload=True,
        )
