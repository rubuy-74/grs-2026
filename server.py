import os
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

# Read environment variables set by docker-compose
SERVER_ID = os.environ.get('SERVER_ID', 'Unknown')
TARGET_HOST = os.environ.get('TARGET_HOST', 'localhost')
PORT = 8000

# Global variable to store the last number received from the other server
last_received = "None"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global last_received
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

        html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Wormhole Server {SERVER_ID}</title></head>
        <body style="font-family: sans-serif; padding: 2rem;">
            <h2>Hello from Server {SERVER_ID}</h2>
            <div style="padding: 1rem; background: #f0f0f0; margin-bottom: 1rem;">
                Last number received from Server {'2' if SERVER_ID == '1' else '1'}: 
                <strong style="font-size: 1.5rem; color: #d32f2f;">{last_received}</strong>
            </div>
            
            <form method="POST" action="/submit">
                <label for="num">Send a number to the other server:</label><br><br>
                <input type="number" id="num" name="num" required>
                <button type="submit">Send</button>
            </form>
        </body>
        </html>
        """
        self.wfile.write(html.encode('utf-8'))

    def do_POST(self):
        global last_received
        
        # Read the POST request body
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')

        if self.path == '/submit':
            # 1. Received a form submission from the browser
            parsed_data = urllib.parse.parse_qs(post_data)
            print(parsed_data)
            num = parsed_data.get('num', [''])[0]

            if num:
                # Forward the number to the OTHER server on the Docker network
                try:
                    url = f"http://{TARGET_HOST}:8000/receive"
                    req = urllib.request.Request(url, data=post_data.encode('utf-8'))
                    urllib.request.urlopen(req)
                except Exception as e:
                    print(f"Error sending data to {TARGET_HOST}: {e}")

            # Redirect the browser back to the main page
            self.send_response(303)
            self.send_header('Location', '/')
            self.end_headers()

        elif self.path == '/receive':
            # 2. Received a payload from the OTHER server
            parsed_data = urllib.parse.parse_qs(post_data)
            last_received = parsed_data.get('num', [''])[0]
            
            # Acknowledge receipt
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == '__main__':
    print(f"Starting Server {SERVER_ID} on port {PORT}. Target is {TARGET_HOST}")
    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()