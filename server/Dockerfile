FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy only requirements first (for caching purposes)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && \
    apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copy server code into /app/server
COPY server /app/server

WORKDIR /app/server

EXPOSE 8765

ENV SERVER_HOST=0.0.0.0 \
    SERVER_PORT=8765 \
    RELOAD=false

CMD ["python", "s1.py"]
