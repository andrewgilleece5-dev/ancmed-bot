FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server ./server
COPY web ./web

ENV ANCMED_DATA_DIR=/data
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000
# Render/Fly set $PORT; fall back to 8000 for local `docker run`.
CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
