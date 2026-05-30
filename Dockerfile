FROM python:3.11-slim

LABEL com.wormhole.hostname=testapp
LABEL com.wormhole.port=8000
LABEL com.wormhole.protocol=http

WORKDIR /app

COPY server.py .

EXPOSE 8000

CMD ["python", "server.py"]