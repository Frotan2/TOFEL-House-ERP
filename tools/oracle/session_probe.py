"""Exercise login and a WebSocket upgrade through the disposable TLS edge."""
import base64
from http.cookiejar import CookieJar
import json
import os
import socket
import ssl
import sys
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener


def probe(ca_file, credentials):
    passwords = [line.removeprefix("Password: ") for line in credentials.splitlines()
                 if line.startswith("Password: ")]
    if len(passwords) != 1 or not passwords[0]:
        raise ValueError("Invalid synthetic credentials file")
    context = ssl.create_default_context(cafile=ca_file)
    base = "https://localhost"
    jar = CookieJar()
    browser = build_opener(HTTPSHandler(context=context), HTTPCookieProcessor(jar))
    form = urlencode({"usr": "Administrator", "pwd": passwords[0]}).encode()
    with browser.open(Request(base + "/api/method/login", data=form), timeout=30) as reply:
        if reply.status != 200 or not any(c.name == "sid" for c in jar):
            raise ValueError("Session creation failed")
    with browser.open(base + "/api/method/frappe.auth.get_logged_user", timeout=30) as reply:
        if json.load(reply).get("message") != "Administrator":
            raise ValueError("Unexpected logged-in identity")
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    handshake = ("GET /socket.io/?EIO=4&transport=websocket HTTP/1.1\r\n"
                 "Host: localhost\r\nOrigin: https://localhost\r\n"
                 "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                 f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
    with socket.create_connection(("localhost", 443), timeout=20) as client:
        with context.wrap_socket(client, server_hostname="localhost") as tls:
            tls.sendall(handshake.encode("ascii"))
            with tls.makefile("rb") as stream:
                if not stream.readline().startswith(b"HTTP/1.1 101 "):
                    raise ValueError("Proxy did not upgrade the websocket connection")
    with browser.open(base + "/api/method/logout", timeout=30) as reply:
        if reply.status != 200:
            raise ValueError("Logout failed")
    print("Verified TLS login, session identity, WebSocket upgrade and logout")


if __name__ == "__main__":
    probe(sys.argv[1], sys.stdin.read())
