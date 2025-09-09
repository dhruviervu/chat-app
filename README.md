## Production-grade Chat App (FastAPI + Streamlit)

### Features
- Multi-user WebSocket chat via FastAPI
- Client UI with Streamlit (select users, per-peer history view)
- AES-GCM end-to-end style encryption with server-provided passphrase
- Env-configurable server/client
- Dockerized with docker-compose for one-command run

### Quick Start (Docker)
1. Optionally copy `.env.example` to `.env` and adjust values.
2. Run:
```bash
docker compose up --build
```
3. Open client: http://localhost:${CLIENT_PORT:-8501}

See `PRODUCTION.md` for a minimal file list and additional deployment options.

### Local Dev (no Docker)
```bash
pip install -r requirements.txt

# Terminal 1: server
cd server
SET SERVER_HOST=127.0.0.1
SET SERVER_PORT=8765
python s1.py

# Terminal 2+: clients
cd client
SET WS_SERVER_URL=ws://127.0.0.1:8765
streamlit run c1.py
```

### Configuration
- Server env: `SERVER_HOST`, `SERVER_PORT`, `DEFAULT_PASSPHRASE`, `MAX_USERS`, `CORS_ALLOW_ORIGINS`
- Client env: `WS_SERVER_URL`

### Notes
- For real production, move passphrase generation/distribution off server default and use per-conversation keys. Persist connections/history in Redis/DB. Add auth and TLS.

