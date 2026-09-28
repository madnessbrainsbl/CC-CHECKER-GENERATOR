from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import mimetypes


ROOT = Path(__file__).resolve().parent
FILES = {
    "/": ROOT / "index.html",
    "/index.html": ROOT / "index.html",
    "/assets/main.css": ROOT / "assets" / "main.css",
    "/assets/index.js": ROOT / "assets" / "index.js",
}


class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        file_path = FILES.get(self.path)
        if file_path is None:
            self.send_error(404)
            return

        try:
            content = file_path.read_bytes()
        except OSError:
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header(
            "Content-Type",
            mimetypes.guess_type(file_path.name)[0] or "application/octet-stream",
        )
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        self.send_error(
            404, "This offline demo does not accept card or payment requests"
        )

    def log_message(self, *_):
        # Request URLs can contain sensitive data; suppress access logging.
        pass


if __name__ == "__main__":
    address = ("127.0.0.1", 9000)
    server = HTTPServer(address, DemoHandler)
    print(f"Offline demo available at http://{address[0]}:{address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
