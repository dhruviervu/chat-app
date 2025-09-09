# app5.py
"""
FastAPI WebSocket server for up to 10 users with chat history.
Auto-detects certs in ./certs; runs TLS if they exist, otherwise plain WS.
User metadata uses 'label' for display name (matches the client).
Run: python app5.py
"""

import json
import os
import traceback
from typing import Dict, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

app = FastAPI()

# connections: username -> WebSocket
connections: Dict[str, WebSocket] = {}
# meta: username -> {"label": str, "anonymous": bool}
meta: Dict[str, Dict[str, object]] = {}
# chat history: "userA_userB" -> list of messages
chat_history: Dict[str, List[Dict]] = {}

MAX_USERS = 10

def get_chat_key(user1: str, user2: str) -> str:
    """Generate a consistent key for chat history between two users."""
    # stable ordering
    a, b = sorted([user1, user2])
    return f"{a}_{b}"

def build_user_list():
    """Return user list for broadcasting: list of dicts with username, label, anonymous"""
    users = []
    for u in list(connections.keys()):
        m = meta.get(u, {"label": u, "anonymous": False})
        users.append({"username": u, "label": m.get("label", u), "anonymous": bool(m.get("anonymous", False))})
    return users

async def broadcast_user_list():
    """Send updated user list to all connected clients (clean dead connections)."""
    payload = {"type": "user_list", "users": build_user_list()}
    text = json.dumps(payload)
    # iterate over a snapshot
    for uname, ws in list(connections.items()):
        try:
            await ws.send_text(text)
        except Exception as e:
            print(f"[server] userlist send failed to {uname}: {e}")
            try:
                await ws.close()
            except Exception:
                pass
            # clean up
            connections.pop(uname, None)
            meta.pop(uname, None)

def _other_user_from_chat_key(chat_key: str, me: str):
    """Given a chat_key like 'a_b', return the other user when 'me' is one of them.
    Returns None if 'me' isn't in the key."""
    # split on the last '_' to be somewhat resilient (usernames with '_' are discouraged)
    parts = chat_key.split('_')
    # If there are exactly 2 parts, simple
    if len(parts) == 2:
        a, b = parts
        if me == a:
            return b
        if me == b:
            return a
        return None
    # fallback: try to find 'me' among parts and return first part that isn't me joined with rest
    if me in parts:
        # remove the first occurrence of me and return the rest joined (best-effort)
        parts_copy = parts.copy()
        parts_copy.remove(me)
        return "_".join(parts_copy)
    return None

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

    # Send recent chat history for this user (best-effort)
    user_chats = {}
    try:
        for chat_key, history in chat_history.items():
            other_user = _other_user_from_chat_key(chat_key, username)
            if other_user:
                # send last 20 messages for that chat
                user_chats[other_user] = history[-20:]
    except Exception as e:
        print(f"[server] error preparing user chats for {username}: {e}")

    if user_chats:
        try:
            await ws.send_text(json.dumps({"type": "chat_history", "chats": user_chats}))
        except Exception:
            pass

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

                # ack to this client
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

                # Validate recipient
                if not recipient or not isinstance(recipient, str):
                    try:
                        await ws.send_text(json.dumps({"type":"error", "reason":"invalid_recipient"}))
                    except Exception:
                        pass
                    continue

                # Store the encrypted message in history
                try:
                    chat_key = get_chat_key(sender_username, recipient)
                    entry = {
                        "sender": sender_display,
                        "sender_username": sender_username,
                        "recipient": recipient,
                        "iv": msg.get("iv"),
                        "ct": msg.get("ct"),
                        "aad": msg.get("aad"),
                        "timestamp": msg.get("timestamp")
                    }
                    chat_history.setdefault(chat_key, []).append(entry)
                    # Keep only last 100 messages per chat
                    if len(chat_history[chat_key]) > 100:
                        chat_history[chat_key] = chat_history[chat_key][-100:]
                except Exception as e:
                    print(f"[server] error storing message: {e}")

                forwarded = {
                    "type": "message",
                    "sender": sender_display,
                    "sender_username": sender_username,
                    "recipient": recipient,
                    "iv": msg.get("iv"),
                    "ct": msg.get("ct"),
                    "aad": msg.get("aad"),
                    "timestamp": msg.get("timestamp")
                }

                if recipient in connections:
                    try:
                        await connections[recipient].send_text(json.dumps(forwarded))
                    except Exception as e:
                        print(f"[server] forward error to {recipient}: {e}")
                        # attempt to notify sender that recipient delivery failed
                        try:
                            await ws.send_text(json.dumps({"type":"error", "reason":"delivery_failed", "recipient": recipient}))
                        except Exception:
                            pass
                else:
                    # recipient offline: notify sender
                    try:
                        await ws.send_text(json.dumps({"type":"error", "reason":"recipient_offline", "recipient": recipient}))
                    except Exception:
                        pass
                continue

            # Request chat history
            if mtype == "get_chat_history":
                other_user = msg.get("with_user")
                if other_user and isinstance(other_user, str):
                    chat_key = get_chat_key(username, other_user)
                    history = chat_history.get(chat_key, [])
                    try:
                        await ws.send_text(json.dumps({
                            "type": "chat_history",
                            "with_user": other_user,
                            "messages": history[-20:]  # Last 20 messages
                        }))
                    except Exception:
                        pass
                continue

            # Unknown type: ignore

    except WebSocketDisconnect:
        print(f"[server] {username} disconnected")
        connections.pop(username, None)
        meta.pop(username, None)
        await broadcast_user_list()
    except Exception as exc:
        print(f"[server] exception for {username}: {exc}")
        traceback.print_exc()
        try:
            if username in connections:
                await connections[username].close()
        except Exception:
            pass
        connections.pop(username, None)
        meta.pop(username, None)
        await broadcast_user_list()

if __name__ == "__main__":
    SSL_CERT = "server/certs/server.crt"
    SSL_KEY = "server/certs/server.key"

    # If certs present and files exist, run with TLS; otherwise non-TLS
    if os.path.exists(SSL_CERT) and os.path.exists(SSL_KEY):
        print("[server] starting with TLS (certs found)")
        uvicorn.run(app, host="127.0.0.1", port=8765, ssl_certfile=SSL_CERT, ssl_keyfile=SSL_KEY, reload=False)
    else:
        print("[server] starting WITHOUT TLS (no certs found). To enable TLS, place certs/server.crt and server.key")
        uvicorn.run(app, host="127.0.0.1", port=8765, reload=False)
