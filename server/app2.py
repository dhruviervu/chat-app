from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json

app = FastAPI()

# Allow all origins for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

connections = {}  # username -> websocket

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await websocket.accept()
    connections[username] = websocket
    print(f"[server] {username} connected")
    try:
        while True:
            data = await websocket.receive_text()
            # Forward to recipient if exists, else broadcast
            try:
                payload = json.loads(data)
                recipient = payload.get("recipient")
                if recipient and recipient in connections:
                    await connections[recipient].send_text(data)
                else:
                    # broadcast
                    for user, ws in connections.items():
                        if user != username:
                            await ws.send_text(data)
            except Exception:
                # fallback: echo back
                await websocket.send_text(data)
    except WebSocketDisconnect:
        print(f"[server] {username} disconnected")
        del connections[username]

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8765, reload=True)
