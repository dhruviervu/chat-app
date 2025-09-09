## Production Run Guide

### Minimal files you need
- `server/s1.py` (FastAPI WebSocket server)
- `client/c1.py` (Streamlit UI)
- `requirements.txt`
- `docker-compose.yml` (includes server, client, redis)
- `server/Dockerfile`, `client/Dockerfile`
- `deploy/traefik-docker-compose.yml` (optional HTTPS)
- `deploy/nginx-site.conf` and `deploy/chat-server.service` (optional VPS setup)

### One-command run (Docker)
```bash
docker compose up --build
```
Then open http://localhost:8501

Environment variables (override as needed):
- SERVER_PORT (default 8765)
- CLIENT_PORT (default 8501)
- DEFAULT_PASSPHRASE
- MAX_USERS (default 50)
- CORS_ALLOW_ORIGINS (default *)
- USE_REDIS (default true)
- REDIS_URL (default redis://redis:6379/0)

### Local run (without Docker)
```bash
pip install -r requirements.txt

# Terminal 1 (server)
set SERVER_HOST=127.0.0.1
set SERVER_PORT=8765
set USE_REDIS=false
python server/s1.py

# Terminal 2 (client)
set WS_SERVER_URL=ws://127.0.0.1:8765
streamlit run client/c1.py
```

### HTTPS with Traefik (Docker)
Edit `deploy/traefik-docker-compose.yml` and set:
- CHAT_DOMAIN, LETSENCRYPT_EMAIL, DEFAULT_PASSPHRASE
Then run:
```bash
cd deploy
docker compose -f traefik-docker-compose.yml up --build -d
```

### VPS with nginx + systemd (no Docker)
1) Copy `deploy/chat-server.service` to `/etc/systemd/system/chat-server.service` and adjust paths/env
2) `sudo systemctl daemon-reload && sudo systemctl enable --now chat-server`
3) Put `deploy/nginx-site.conf` as a site, replace domain, then `sudo nginx -s reload`

