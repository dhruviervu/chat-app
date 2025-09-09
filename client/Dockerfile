FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install dependencies
COPY ../requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy client source
COPY . /app/client
WORKDIR /app/client

EXPOSE 8501

# Default WS server URL; override in compose or env as needed
ENV WS_SERVER_URL=ws://server:8765

CMD ["streamlit", "run", "c1.py", "--server.port=8501", "--server.address=0.0.0.0"]
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install Streamlit and other dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY client /app/client

WORKDIR /app/client

EXPOSE 8501

ENV WS_SERVER_URL=ws://server:8765

CMD ["streamlit", "run", "c1.py", "--server.port=8501", "--server.address=0.0.0.0"]
