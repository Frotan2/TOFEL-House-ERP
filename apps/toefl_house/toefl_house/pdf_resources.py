"""Offline, bounded resource policy for the installed beta PDF renderer.

Never delegate to WeasyPrint's default fetcher: even same-origin HTTP requests
could expose an internal API or redirect to a private host. URLs are mapped to
trusted app assets or authorized image attachments without DNS or HTTP. Every
CSS import, font, SVG subresource and PDF attachment uses the same fetcher.
"""
from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path
import stat
from urllib.parse import unquote, urlsplit

MAX_RESOURCE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024
MAX_RESOURCES = 128
ASSET_TYPES = {
    ".css": "text/css", ".woff": "font/woff", ".woff2": "font/woff2",
    ".ttf": "font/ttf", ".otf": "font/otf", ".svg": "image/svg+xml",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp",
}
RASTER_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


class PDFResourceDenied(ValueError):
    """Generic message intentionally omits URLs, paths and document contents."""


def _raster_matches(data: bytes, mime: str) -> bool:
    return {
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": data.startswith(b"\xff\xd8\xff"),
        "image/gif": data.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
    }.get(mime, False)


def _read_beneath(root: Path, parts: list[str]) -> bytes:
    """Open relative to directory FDs; no symlinks, devices or check/use races.

    Product containers are Linux. Do not silently weaken this policy on a
    platform lacking O_NOFOLLOW or dir_fd support. Trusted root paths are
    provided by server configuration, never by the rendered document.
    """
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(leaf, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_RESOURCE_BYTES:
                raise PDFResourceDenied("PDF resource blocked by policy")
            data = stream.read(MAX_RESOURCE_BYTES + 1)
            if len(data) > MAX_RESOURCE_BYTES:
                raise PDFResourceDenied("PDF resource blocked by policy")
            return data
    finally:
        os.close(fd)


class ResourcePolicy:
    def __init__(self, *, base_url: str, assets: dict[str, Path], attachment_reader):
        base = urlsplit(base_url)
        if base.scheme not in ("https", "http") or not base.netloc or base.username or base.password:
            raise PDFResourceDenied("Invalid PDF site origin")
        self.origin = (base.scheme, base.netloc)
        self.assets = assets
        self.attachment_reader = attachment_reader
        self.count = 0
        self.total = 0
        self.denied = False

    def __call__(self, url: str, *args, **kwargs) -> dict:
        # WeasyPrint normally swallows fetch errors and emits an incomplete
        # PDF. Record the failure so render_pdf refuses that misleading result.
        try:
            self.count += 1
            if self.count > MAX_RESOURCES or not isinstance(url, str) or len(url) > MAX_RESOURCE_BYTES * 2:
                raise ValueError
            data, mime = self._fetch(url)
            self.total += len(data)
            if len(data) > MAX_RESOURCE_BYTES or self.total > MAX_TOTAL_BYTES:
                raise ValueError
            return {"string": data, "mime_type": mime}
        except Exception:
            self.denied = True
            raise PDFResourceDenied("PDF resource blocked by policy") from None

    def check(self) -> None:
        if self.denied:
            raise PDFResourceDenied("PDF contains unavailable or disallowed resources; use local app assets or authorized image attachments")

    def _fetch(self, url: str) -> tuple[bytes, str]:
        if any(ord(char) < 32 or ord(char) == 127 for char in url) or "\\" in url:
            raise ValueError
        parsed = urlsplit(url)
        if parsed.scheme == "data":
            header, separator, payload = url.partition(",")
            mime = header[5:].removesuffix(";base64")
            if not separator or header != f"data:{mime};base64" or mime not in RASTER_TYPES:
                raise ValueError
            try:
                data = base64.b64decode(payload, validate=True)
            except binascii.Error:
                raise ValueError from None
            if not _raster_matches(data, mime):
                raise ValueError
            return data, mime
        if (parsed.scheme, parsed.netloc) != self.origin or parsed.username or parsed.password:
            raise ValueError
        path = unquote(parsed.path, errors="strict")
        if "%" in path or "\\" in path or any(ord(c) < 32 or ord(c) == 127 for c in path):
            raise ValueError
        parts = path.split("/")
        if not path.startswith("/") or any(p in ("", ".", "..") for p in parts[1:]):
            raise ValueError
        mime = ASSET_TYPES.get(Path(path).suffix.lower())
        if not mime:
            raise ValueError
        for prefix, root in self.assets.items():
            if path.startswith(prefix):
                return _read_beneath(root, path[len(prefix):].split("/")), mime
        if not path.startswith(("/files/", "/private/files/")) or mime not in RASTER_TYPES:
            raise ValueError
        # Attachment lookup is exact and authorization happens before file IO.
        data = self.attachment_reader(path)
        if not _raster_matches(data, mime):
            raise ValueError
        return data, mime


def resource_policy(doc, base_url: str) -> ResourcePolicy:
    import frappe

    assets = {
        f"/assets/{app}/": Path(frappe.get_app_path(app, "public")).resolve()
        for app in frappe.get_installed_apps()
    }

    def attachment_reader(path: str) -> bytes:
        files = frappe.get_all("File", filters={
            "file_url": path, "attached_to_doctype": doc.doctype, "attached_to_name": doc.name,
        }, pluck="name", limit_page_length=2)
        if len(files) != 1:
            raise PDFResourceDenied("PDF resource blocked by policy")
        attachment = frappe.get_doc("File", files[0])
        attachment.check_permission("read")
        if not frappe.has_permission("File", "read", attachment):
            raise PDFResourceDenied("PDF resource blocked by policy")
        private = path.startswith("/private/files/")
        if bool(attachment.is_private) != private:
            raise PDFResourceDenied("PDF resource blocked by policy")
        root = Path(frappe.get_site_path("private" if private else "public", "files")).resolve()
        prefix = "/private/files/" if private else "/files/"
        return _read_beneath(root, path[len(prefix):].split("/"))

    return ResourcePolicy(base_url=base_url, assets=assets, attachment_reader=attachment_reader)
