"""Local-only HTTP fixture for disposable Windows online-installer tests.

Never serves, reads, or writes any TOEFL House database. Deliberately plain
HTTP: the production online bootstrap rejects HTTP, while TEST_BUILD accepts
loopback solely to exercise ranged-download mechanics without real releases.
"""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import sys


def main() -> None:
    payload = Path(sys.argv[1]).read_bytes()
    port_file = Path(sys.argv[2])
    log_file = Path(sys.argv[3])

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/setup":
                self.send_error(404)
                return
            header = self.headers.get("Range", "")
            with log_file.open("a", encoding="ascii") as log:
                log.write(header or "FULL")
                log.write("\n")
            start = 0
            match = re.fullmatch(r"bytes=(\d+)-", header)
            if header:
                if match is None:
                    self.send_error(400)
                    return
                start = int(match.group(1))
                if start >= len(payload):
                    self.send_response(416)
                    self.end_headers()
                    return
            data = payload[start:]
            self.send_response(206 if header else 200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            if header:
                self.send_header("Content-Range", f"bytes {start}-{len(payload)-1}/{len(payload)}")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    try:
        port_file.write_text(str(server.server_port), encoding="ascii")
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
