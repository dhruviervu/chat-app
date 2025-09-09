import json
import os
import asyncio
import traceback
from typing import Dict, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis
import uvicorn
import secrets

app = FastAPI()

# CORS (configurable via CORS_ALLOW_ORIGINS)
_allow_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "*")
_allow_origins = [o.strip() for o in _allow_origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# TODO: Replace these in-memory dicts with persistent store like Redis or DB
connections: Dict[str, WebSocket] = {}
meta: Dict[str, Dict[str, object]] = {}
chat_history: Dict[str, List[Dict]] = {}

DEFAULT_PASSPHRASE = os.getenv("DEFAULT_PASSPHRASE", "xQ9#kL2$pR7&mZ4!vW1@cN6^bV3*sY8")

MAX_USERS = int(os.getenv("MAX_USERS", "10"))

SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8765"))
RELOAD = os.getenv("RELOAD", "false").lower() in ("1", "true", "yes", "on")
USE_REDIS = os.getenv("USE_REDIS", "false").lower() in ("1", "true", "yes", "on")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_redis_client = None

async def get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client

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
            try: await ws.close()
            except Exception: pass
            connections.pop(uname, None)
            meta.pop(uname, None)

def _other_user_from_chat_key(chat_key: str, me: str):
    parts = chat_key.split('_')
    if len(parts) == 2:
        a, b = parts
        return b if me == a else a if me == b else None
    if me in parts:
        parts_copy = parts.copy()
        parts_copy.remove(me)
        return "_".join(parts_copy)
    return None

@app.websocket("/ws/{username}")
async def ws_endpoint(ws: WebSocket, username: str):
    await ws.accept()

    if username in connections:
        await ws.send_text(json.dumps({"type":"register_failed", "reason":"username_taken"}))
        await ws.close()
        return

    if len(connections) >= MAX_USERS:
        await ws.send_text(json.dumps({"type":"register_failed", "reason":"server_full"}))
        await ws.close()
        return

    try:
        await ws.send_text(json.dumps({
            "type": "passphrase",
            "passphrase": DEFAULT_PASSPHRASE
        }))
    except Exception as e:
        print(f"[server] failed to send passphrase to {username}: {e}")
        await ws.close()
        return

    connections[username] = ws
    meta[username] = {"label": username, "anonymous": False}
    print(f"[server] {username} connected — total {len(connections)}")

    # If Redis is enabled, subscribe to this user's delivery channel
    redis_task = None
    pubsub = None
    if USE_REDIS:
        try:
            redis = await get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe(f"chat:deliver:{username}")

            async def redis_consumer():
                try:
                    async for message in pubsub.listen():
                        if message.get("type") != "message":
                            continue
                        data = message.get("data")
                        if not data:
                            continue
                        try:
                            await ws.send_text(data)
                        except Exception:
                            break
                finally:
                    try:
                        await pubsub.unsubscribe(f"chat:deliver:{username}")
                    except Exception:
                        pass

            redis_task = asyncio.create_task(redis_consumer())
        except Exception as e:
            print(f"[server] failed to init redis subscriber for {username}: {e}")

    user_chats = {}
    try:
        for chat_key, history in chat_history.items():
            other_user = _other_user_from_chat_key(chat_key, username)
            if other_user:
                user_chats[other_user] = history[-20:]
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
                    await ws.send_text(json.dumps({"type":"error", "reason":"malformed_json"}))
                except Exception:
                    pass
                continue

            mtype = msg.get("type")

            if mtype == "register":
                incoming_username = msg.get("username", username)
                if incoming_username != username:
                    await ws.send_text(json.dumps({"type":"register_failed", "reason":"username_mismatch"}))
                    await ws.close()
                    return

                anon_flag = bool(msg.get("anonymous", False))
                label = msg.get("label") or ("Anon-" + secrets.token_hex(3) if anon_flag else username)

                meta[username] = {"label": label, "anonymous": anon_flag}

                try:
                    await ws.send_text(json.dumps({"type":"register_ok", "username": username, "label": label, "passphrase": DEFAULT_PASSPHRASE}))
                except Exception:
                    pass

                # Resend passphrase after registration to avoid races
                try:
                    await ws.send_text(json.dumps({
                        "type": "passphrase",
                        "passphrase": DEFAULT_PASSPHRASE
                    }))
                except Exception:
                    pass

                await broadcast_user_list()
                continue

            if mtype == "message":
                sender_username = msg.get("sender_username") or username
                recipient = msg.get("recipient")
                sender_display = meta.get(sender_username, {}).get("label", sender_username)

                if not recipient or not isinstance(recipient, str):
                    try:
                        await ws.send_text(json.dumps({"type":"error", "reason":"invalid_recipient"}))
                    except Exception:
                        pass
                    continue

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

                is_local = recipient in connections
                if is_local:
                    try:
                        await connections[recipient].send_text(json.dumps(forwarded))
                    except Exception as e:
                        print(f"[server] forward error to {recipient}: {e}")
                        try:
                            await ws.send_text(json.dumps({"type":"error", "reason":"delivery_failed", "recipient": recipient}))
                        except Exception:
                            pass
                else:
                    if USE_REDIS:
                        # Publish for cross-instance delivery; don't mark offline since remote instance may deliver
                        try:
                            redis = await get_redis()
                            await redis.publish(f"chat:deliver:{recipient}", json.dumps(forwarded))
                        except Exception as e:
                            print(f"[server] redis publish error: {e}")
                    else:
                        try:
                            await ws.send_text(json.dumps({"type":"error", "reason":"recipient_offline", "recipient": recipient}))
                        except Exception:
                            pass
                continue

            if mtype == "get_chat_history":
                other_user = msg.get("with_user")
                if other_user and isinstance(other_user, str):
                    chat_key = get_chat_key(username, other_user)
                    history = chat_history.get(chat_key, [])
                    try:
                        await ws.send_text(json.dumps({
                            "type": "chat_history",
                            "with_user": other_user,
                            "messages": history[-20:]
                        }))
                    except Exception:
                        pass
                continue

            if mtype == "get_passphrase":
                try:
                    await ws.send_text(json.dumps({
                        "type": "passphrase",
                        "passphrase": DEFAULT_PASSPHRASE
                    }))
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
    finally:
        if redis_task:
            try:
                redis_task.cancel()
            except Exception:
                pass
        if pubsub:
            try:
                await pubsub.close()
            except Exception:
                pass

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"service": "chat-server", "websocket_path": "/ws/{username}", "max_users": MAX_USERS}

if __name__ == "__main__":
    print(f"[server] starting WITHOUT TLS on {SERVER_HOST}:{SERVER_PORT}")
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, reload=RELOAD)
