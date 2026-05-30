FROM python:3.11-slim

WORKDIR /app
RUN printf "from http.server import BaseHTTPRequestHandler, HTTPServer\n\nclass Handler(BaseHTTPRequestHandler):\n    def do_GET(self):\n        self.send_response(200)\n        self.end_headers()\n        self.wfile.write(b'Hello from wormhole test')\n\nHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()\n" > server.py

CMD ["python", "server.py"]