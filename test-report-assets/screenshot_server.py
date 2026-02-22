"""Tiny HTTP server to receive screenshots from the browser via POST."""
import http.server
import json
import base64
import os

SAVE_DIR = os.path.dirname(os.path.abspath(__file__))

class ScreenshotHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length)
        data = json.loads(body)

        filename = data.get('filename', 'screenshot.png')
        image_data = data.get('image', '')

        # Remove data URL prefix if present
        if ',' in image_data:
            image_data = image_data.split(',', 1)[1]

        filepath = os.path.join(SAVE_DIR, filename)
        with open(filepath, 'wb') as f:
            f.write(base64.b64decode(image_data))

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({'status': 'ok', 'path': filepath}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        print(f"[ScreenshotServer] {args[0]}")

if __name__ == '__main__':
    server = http.server.HTTPServer(('127.0.0.1', 9876), ScreenshotHandler)
    print(f"Screenshot server listening on http://127.0.0.1:9876")
    print(f"Saving to: {SAVE_DIR}")
    server.serve_forever()
