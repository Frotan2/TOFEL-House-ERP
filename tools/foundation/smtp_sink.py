"""A real SMTP receiver, written against the socket API only.

Alert delivery has to be shown arriving somewhere, and "somewhere" has to be a real
process holding a real socket rather than a stub that returns success. Python 3.12
removed ``smtpd`` and ``asyncore`` from the standard library, and ``aiosmtpd`` is a
third-party dependency this stack does not carry, so the sink speaks just enough of
RFC 5321 to complete a transaction with a real ``smtplib`` client:

    220 greeting -> EHLO/HELO -> MAIL FROM -> RCPT TO -> DATA -> . -> QUIT

Everything the client sends after ``DATA`` is kept verbatim, so the probe can assert
on the message that actually crossed the socket - recipients, subject and body -
instead of on a flag a mock set.

The sink is deliberately dumb in one way that matters: it accepts every message. A
receiver that also decided what to reject would make it impossible to tell a delivery
failure from a policy decision, and the probe needs delivery failures to be the
server's fault alone.
"""
import socket
import threading


class SmtpSink:
    """A single-threaded-per-connection SMTP sink that records what it receives."""

    def __init__(self, host="127.0.0.1", port=0, hostname="sink.foundation.internal"):
        self.host = host
        self.hostname = hostname
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind((host, port))
        self._listener.listen(8)
        # A timeout is what makes the sink stoppable. A thread blocked in accept()
        # keeps the underlying file description alive even after close(), so the port
        # stays in LISTEN and the probe could not demonstrate fail-closed behaviour
        # when the receiver is removed. Polling the stop event instead lets the loop
        # exit and release the port for real.
        self._listener.settimeout(0.25)
        self.port = self._listener.getsockname()[1]
        self.messages = []
        self.connections = 0
        self._stop = threading.Event()
        self._threads = []
        self.error = None
        self.stopped = False

    def start(self):
        thread = threading.Thread(target=self._accept_loop, daemon=True)
        thread.start()
        self._threads.append(thread)
        return self

    def stop(self):
        """Stop accepting and release the port, so removal is observable."""
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=5)
        try:
            self._listener.close()
        except OSError:
            pass
        self.stopped = True

    @property
    def address(self):
        return f"{self.host}:{self.port}"

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                connection, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            self.connections += 1
            handler = threading.Thread(target=self._serve, args=(connection,), daemon=True)
            handler.start()
            self._threads.append(handler)

    def _serve(self, connection):
        try:
            connection.settimeout(30)
            handle = connection.makefile("rwb")
            handle.write(f"220 {self.hostname} ESMTP foundation sink ready\r\n".encode())
            handle.flush()
            while not self._stop.is_set():
                line = handle.readline()
                if not line:
                    break
                text = line.decode("utf-8", "replace").rstrip("\r\n")
                verb = text.split(":", 1)[0].upper()
                if verb in ("EHLO", "HELO"):
                    if verb == "EHLO":
                        handle.write(b"250-" + self.hostname.encode() + b"\r\n")
                        handle.write(b"250-SIZE 33554432\r\n")
                        handle.write(b"250-8BITMIME\r\n")
                        handle.write(b"250 HELP\r\n")
                    else:
                        handle.write(b"250 " + self.hostname.encode() + b"\r\n")
                elif verb.startswith("MAIL"):
                    handle.write(b"250 2.1.0 Ok\r\n")
                elif verb.startswith("RCPT"):
                    handle.write(b"250 2.1.5 Ok\r\n")
                elif verb == "DATA":
                    handle.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                    handle.flush()
                    body = []
                    while True:
                        chunk = handle.readline()
                        if not chunk:
                            break
                        if chunk in (b".\r\n", b".\n"):
                            break
                        # Undo the transparency dot-stuffing a client performs.
                        body.append(chunk[1:] if chunk.startswith(b"..") else chunk)
                    handle.write(b"250 2.0.0 Ok: queued as FOUNDATION\r\n")
                    self.messages.append({"raw": b"".join(body).decode("utf-8", "replace"),
                                          "envelope": text})
                elif verb == "RSET":
                    handle.write(b"250 2.0.0 Ok\r\n")
                elif verb == "NOOP":
                    handle.write(b"250 2.0.0 Ok\r\n")
                elif verb == "QUIT":
                    handle.write(b"221 2.0.0 Bye\r\n")
                    handle.flush()
                    break
                else:
                    handle.write(b"250 2.0.0 Ok\r\n")
                handle.flush()
        except (OSError, UnicodeDecodeError) as exc:
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                connection.close()
            except OSError:
                pass


def parse_message_headers(raw):
    """Read the headers a probe needs out of a received message.

    Parsed by hand because the point is to read what arrived on the socket, not what
    a library would have constructed. Only the header block is examined; the body is
    returned separately so a probe can assert on content too.
    """
    text = raw or ""
    head, _, body = text.partition("\r\n\r\n")
    if not _:
        head, _, body = text.partition("\n\n")
    headers = {}
    current = None
    for line in head.splitlines():
        if not line.strip():
            continue
        if line[0] in (" ", "\t") and current:
            headers[current] = (headers[current] + " " + line.strip()).strip()
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            current = key.strip().lower()
            headers[current] = value.strip()
    return {"headers": headers, "body": body,
            "subject": headers.get("subject"),
            "to": headers.get("to"), "from": headers.get("from"),
            "message_id": headers.get("message-id")}
