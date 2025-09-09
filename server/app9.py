# app8_fixed.py
"""
app8_fixed.py — WebSocket chat server (TLS auto-detect, runtime alias updates).
Drop-in replacement for your app8.py with more robust TLS start and clearer logs.
Run: python app8_fixed.py
"""

import json
import os
import traceback
import secrets
from typing import Dict, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

app = FastAPI()

connections: Dict[str, WebSocket] = {}
meta: Dict[str, Dict[str, object]] = {}
chat_history: Dict[str, List[Dict]] = {}

MAX_USERS = 10


def get_chat_key(user1: str, user2: str) -> str:
    a, b = sorted([user1, user2])
    return f"{a}_{b}"


def build_user_list():
    users = []
    for u in list(connections.keys()):
        m = meta.get(u, {"label": u, "anonymous": False})
        users.append({"username": u, "label": m.get("label", u), "anonymous": bool(m.get("anonymous", False))})
    return users


async def broadcast_user_list():
    payload = {"type": "user_list", "users": build_user_list()}
    text = json.dumps(payload)
    for uname, ws in list(connections.items()):
        try:
            await ws.send_text(text)
        except Exception as e:
            print(f"[server] userlist send failed to {uname}: {e}")
            try:
                await ws.close()
            except Exception:
                pass
            connections.pop(uname, None)
            meta.pop(uname, None)


def _other_user_from_chat_key(chat_key: str, me: str):
    parts = chat_key.split("_")
    if len(parts) == 2:
        a, b = parts
        if me == a:
            return b
        if me == b:
            return a
        return None
    if me in parts:
        parts_copy = parts.copy()
        parts_copy.remove(me)
        return "_".join(parts_copy)
    return None


@app.websocket("/ws/{username}")
async def ws_endpoint(ws: WebSocket, username: str):
    await ws.accept()

    if username in connections:
        await ws.send_text(json.dumps({"type": "register_failed", "reason": "username_taken"}))
        await ws.close()
        return

    if len(connections) >= MAX_USERS:
        await ws.send_text(json.dumps({"type": "register_failed", "reason": "server_full"}))
        await ws.close()
        return

    connections[username] = ws
    meta[username] = {"label": username, "anonymous": False}
    print(f"[server] {username} connected — total {len(connections)}")

    # Send recent chat history (enriched)
    user_chats = {}
    try:
        for chat_key, history in chat_history.items():
            other_user = _other_user_from_chat_key(chat_key, username)
            if other_user:
                enriched = []
                for m in history[-20:]:
                    enriched.append(
                        {
                            **m,
                            "sender": meta.get(m["sender_username"], {}).get("label", m["sender_username"])
                        }
                    )
                user_chats[other_user] = enriched
    except Exception as e:
        print(f"[server] error preparing user chats for {username}: {e}")

    if user_chats:
        try:
            await ws.send_text(json.dumps({"type": "chat_history", "chats": user_chats}))
        except Exception:
            pass

    await broadcast_user_list()

    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
            except Exception:
                try:
                    await ws.send_text(json.dumps({"type": "error", "reason": "malformed_json"}))
                except Exception:
                    pass
                continue

            mtype = msg.get("type")

            if mtype == "register":
                incoming_username = msg.get("username", username)
                if incoming_username != username:
                    await ws.send_text(json.dumps({"type": "register_failed", "reason": "username_mismatch"}))
                    await ws.close()
                    return

                anon_flag = bool(msg.get("anonymous", False))
                label = msg.get("label")
                if anon_flag:
                    if not label:
                        label = "Anon-" + secrets.token_hex(3)
                else:
                    label = username

                meta[username] = {"label": label, "anonymous": anon_flag}

                try:
                    await ws.send_text(json.dumps({"type": "register_ok", "username": username, "label": label}))
                except Exception:
                    pass

                await broadcast_user_list()
                continue

            if mtype == "update_label":
                new_label = msg.get("label")
                anon_flag = bool(msg.get("anonymous", False))
                if anon_flag and not new_label:
                    new_label = "Anon-" + secrets.token_hex(3)
                if not anon_flag:
                    new_label = username
                meta[username] = {"label": new_label, "anonymous": anon_flag}
                try:
                    await ws.send_text(json.dumps({"type": "update_ok", "label": new_label, "anonymous": anon_flag}))
                except Exception:
                    pass
                await broadcast_user_list()
                continue

            if mtype == "message":
                sender_username = msg.get("sender_username") or username
                recipient = msg.get("recipient")
                if not recipient or not isinstance(recipient, str):
                    try:
                        await ws.send_text(json.dumps({"type": "error", "reason": "invalid_recipient"}))
                    except Exception:
                        pass
                    continue

                try:
                    chat_key = get_chat_key(sender_username, recipient)
                    entry = {
                        "sender_username": sender_username,
                        "recipient": recipient,
                        "iv": msg.get("iv"),
                        "ct": msg.get("ct"),
                        "aad": msg.get("aad"),
                        "timestamp": msg.get("timestamp")
                    }
                    chat_history.setdefault(chat_key, []).append(entry)
                    if len(chat_history[chat_key]) > 100:
                        chat_history[chat_key] = chat_history[chat_key][-100:]
                except Exception as e:
                    print(f"[server] error storing message: {e}")

                forwarded = {
                    "type": "message",
                    "sender_username": sender_username,
                    "sender": meta.get(sender_username, {}).get("label", sender_username),
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
                        try:
                            await ws.send_text(json.dumps({"type": "error", "reason": "delivery_failed", "recipient": recipient}))
                        except Exception:
                            pass
                else:
                    try:
                        await ws.send_text(json.dumps({"type": "error", "reason": "recipient_offline", "recipient": recipient}))
                    except Exception:
                        pass
                continue

            if mtype == "get_chat_history":
                other_user = msg.get("with_user")
                if other_user and isinstance(other_user, str):
                    chat_key = get_chat_key(username, other_user)
                    history = chat_history.get(chat_key, [])
                    enriched = []
                    for m in history[-20:]:
                        enriched.append({
                            **m,
                            "sender": meta.get(m["sender_username"], {}).get("label", m["sender_username"])
                        })
                    try:
                        await ws.send_text(json.dumps({"type": "chat_history", "with_user": other_user, "messages": enriched}))
                    except Exception:
                        pass
                continue

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
    # TLS cert paths (relative)
    SSL_CERT = os.path.join("certs", "server.crt")
    SSL_KEY = os.path.join("certs", "server.key")

    # Create certs dir for convenience (won't create cert files)
    os.makedirs(os.path.dirname(SSL_CERT), exist_ok=True)

    use_tls = os.path.exists(SSL_CERT) and os.path.exists(SSL_KEY)
    if use_tls:
        print(f"[server] TLS certs found at {SSL_CERT} and {SSL_KEY}")
        try:
            # Try starting with TLS; if it fails, we'll show the error and fallback to non-TLS.
            uvicorn.run(app, host="127.0.0.1", port=8765, ssl_certfile=SSL_CERT, ssl_keyfile=SSL_KEY, reload=False)
        except Exception as e:
            print(f"[server] failed to start TLS server: {e}")
            print("[server] falling back to plain WS (non-TLS). Check certificate paths and SAN/CN validity.")
            uvicorn.run(app, host="127.0.0.1", port=8765, reload=False)
    else:
        print("[server] starting WITHOUT TLS (no certs found). To enable TLS place server/certs/server.crt and server.key")
        uvicorn.run(app, host="127.0.0.1", port=8765, reload=False)
