# app5_fixed.py
"""
FastAPI WebSocket server for up to 10 users.
Auto-detects certs in ./certs; runs TLS if they exist, otherwise plain WS.
User metadata uses 'label' for display name (matches the client).
Run: python app5_fixed.py
Or run with uvicorn: uvicorn app5_fixed:app --host 127.0.0.1 --port 8765
"""

import json
import os
import traceback
from typing import Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

app = FastAPI()

# connections: username -> WebSocket
connections: Dict[str, WebSocket] = {}
# meta: username -> {"label": str, "anonymous": bool}
meta: Dict[str, Dict[str, object]] = {}

MAX_USERS = 10

def build_user_list():
    """Return user list for broadcasting: list of dicts with username, label, anonymous"""
    users = []
    # iterate keys in stable order
    for u in list(connections.keys()):
        m = meta.get(u, {"label": u, "anonymous": False})
        users.append({"username": u, "label": m.get("label", u), "anonymous": bool(m.get("anonymous", False))})
    return users

async def broadcast_user_list():
    """Send updated user list to all connected clients"""
    payload = {"type": "user_list", "users": build_user_list()}
    text = json.dumps(payload)
    for uname, ws in list(connections.items()):
        try:
            await ws.send_text(text)
        except Exception as e:
            # if send fails, disconnect that client
            print(f"[server] userlist send failed to {uname}: {e}")
            try:
                await ws.close()
            except Exception:
                pass
            if uname in connections:
                del connections[uname]
            if uname in meta:
                del meta[uname]

@app.websocket("/ws/{username}")
async def ws_endpoint(ws: WebSocket, username: str):
    # Accept connection
    await ws.accept()

    # Enforce uniqueness
    if username in connections:
        await ws.send_text(json.dumps({"type":"register_failed", "reason":"username_taken"}))
        await ws.close()
        return

    # Enforce max users
    if len(connections) >= MAX_USERS:
        await ws.send_text(json.dumps({"type":"register_failed", "reason":"server_full"}))
        await ws.close()
        return

    # Tentatively register connection with default meta (will be updated on 'register')
    connections[username] = ws
    meta[username] = {"label": username, "anonymous": False}
    print(f"[server] {username} connected — total {len(connections)}")

    # Broadcast new user list
    await broadcast_user_list()

    try:
        while True:
            data = await ws.receive_text()
            # parse JSON safely
            try:
                msg = json.loads(data)
            except Exception:
                # ignore malformed messages but optionally send an error
                try:
                    await ws.send_text(json.dumps({"type":"error", "reason":"malformed_json"}))
                except Exception:
                    pass
                continue

            mtype = msg.get("type")

            # Registration message
            if mtype == "register":
                incoming_username = msg.get("username", username)
                if incoming_username != username:
                    await ws.send_text(json.dumps({"type":"register_failed", "reason":"username_mismatch"}))
                    await ws.close()
                    return

                # update meta
                anon_flag = bool(msg.get("anonymous", False))
                label = msg.get("label")
                if anon_flag:
                    if not label:
                        import secrets
                        label = "Anon-" + secrets.token_hex(3)
                else:
                    label = username

                meta[username] = {"label": label, "anonymous": anon_flag}

                # ack to this client (use label key to match client)
                try:
                    await ws.send_text(json.dumps({"type":"register_ok", "username": username, "label": label}))
                except Exception:
                    pass

                # notify all clients with updated user list
                await broadcast_user_list()
                continue

            # Chat message
            if mtype == "message":
                sender_username = msg.get("sender_username") or username
                recipient = msg.get("recipient")
                sender_display = meta.get(sender_username, {}).get("label", sender_username)
                forwarded = dict(msg)
                forwarded["sender"] = sender_display
                forwarded["sender_username"] = sender_username

                if recipient and recipient in connections:
                    try:
                        await connections[recipient].send_text(json.dumps(forwarded))
                    except Exception as e:
                        print(f"[server] forward error to {recipient}: {e}")
                else:
                    # recipient offline: notify sender
                    try:
                        await ws.send_text(json.dumps({"type":"error", "reason":"recipient_offline", "recipient": recipient}))
                    except Exception:
                        pass
                continue

            # Unknown type: ignore (or log)
            # optionally: handle ping/pong
            # else: ignore

    except WebSocketDisconnect:
        print(f"[server] {username} disconnected")
        if username in connections:
            del connections[username]
        if username in meta:
            del meta[username]
        await broadcast_user_list()
    except Exception as exc:
        print(f"[server] exception for {username}: {exc}")
        traceback.print_exc()
        if username in connections:
            try:
                await connections[username].close()
            except Exception:
                pass
            del connections[username]
        if username in meta:
            del meta[username]
        await broadcast_user_list()

if __name__ == "__main__":
    SSL_CERT = "certs/server.crt"
    SSL_KEY = "certs/server.key"

    # If certs present and files exist, run with TLS; otherwise non-TLS
    if os.path.exists(SSL_CERT) and os.path.exists(SSL_KEY):
        print("[server] starting with TLS (certs found)")
        uvicorn.run(app, host="127.0.0.1", port=8765, ssl_certfile=SSL_CERT, ssl_keyfile=SSL_KEY, reload=False)
    else:
        print("[server] starting WITHOUT TLS (no certs found). To enable TLS, place certs/server.crt and server.key")
        uvicorn.run(app, host="127.0.0.1", port=8765, reload=False)
