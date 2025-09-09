# server_webrtc.py
import json
import traceback
from typing import Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

app = FastAPI()

connections: Dict[str, WebSocket] = {}

@app.websocket("/ws/{username}")
async def ws_endpoint(ws: WebSocket, username: str):
    await ws.accept()
    if username in connections:
        await ws.close()
        return
    connections[username] = ws
    print(f"[server] {username} connected")

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            recipient = msg.get("recipient")
            if recipient in connections:
                try:
                    await connections[recipient].send_text(json.dumps(msg))
                except Exception as e:
                    print(f"[server] send failed to {recipient}: {e}")
            else:
                # bounce back error if user offline
                await ws.send_text(json.dumps({"type": "error", "reason": "recipient_offline"}))
    except WebSocketDisconnect:
        print(f"[server] {username} disconnected")
        connections.pop(username, None)
    except Exception as e:
        print(f"[server] exception: {e}")
        traceback.print_exc()
        connections.pop(username, None)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)
