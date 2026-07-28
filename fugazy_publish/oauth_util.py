"""Shared OAuth helpers for native social platform clients."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import secrets
import ssl
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from fugazy_publish.config import AppConfig, credentials_dir


def cred_path(config: AppConfig, name: str) -> Path:
    return credentials_dir(config) / name


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def tiktok_pkce_pair() -> tuple[str, str]:
    """TikTok Desktop Login Kit uses hex(SHA256(verifier)), not base64url."""
    verifier = secrets.token_urlsafe(64)
    challenge = hashlib.sha256(verifier.encode("ascii")).hexdigest()
    return verifier, challenge


def basic_auth_header(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def token_expired(token: dict[str, Any], *, skew_seconds: int = 120) -> bool:
    expires_at = token.get("expires_at")
    if expires_at is None:
        return False
    return time.time() >= float(expires_at) - skew_seconds


def with_expiry(token: dict[str, Any], expires_in: int | float) -> dict[str, Any]:
    merged = dict(token)
    merged["expires_at"] = time.time() + float(expires_in)
    return merged


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    auth_code: str | None = None
    auth_error: str | None = None
    expected_state: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        query = parse_qs(urlparse(self.path).query)
        if _OAuthCallbackHandler.expected_state is not None:
            state_vals = query.get("state", [])
            if not state_vals or state_vals[0] != _OAuthCallbackHandler.expected_state:
                body = b"<html><body><h2>Stale auth tab. Close this and use the latest browser window.</h2></body></html>"
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        if "code" in query:
            _OAuthCallbackHandler.auth_code = query["code"][0]
            body = b"<html><body><h2>Authorized. You can close this tab.</h2></body></html>"
            status = 200
        else:
            _OAuthCallbackHandler.auth_error = query.get("error", ["unknown"])[0]
            body = b"<html><body><h2>Authorization failed.</h2></body></html>"
            status = 400
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def ensure_localhost_cert(cert_dir: Path) -> tuple[Path, Path]:
    """Self-signed cert for Meta/Facebook OAuth (requires HTTPS redirect URIs)."""
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / "oauth-localhost.crt"
    key_path = cert_dir / "oauth-localhost.key"
    if cert_path.is_file() and key_path.is_file():
        return cert_path, key_path

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def wait_for_oauth_code(
    port: int = 8765,
    *,
    timeout: float = 180.0,
    expected_state: str | None = None,
    use_https: bool = False,
    cert_dir: Path | None = None,
) -> str:
    _OAuthCallbackHandler.auth_code = None
    _OAuthCallbackHandler.auth_error = None
    _OAuthCallbackHandler.expected_state = expected_state
    host = "localhost" if use_https else "127.0.0.1"
    server = HTTPServer((host, port), _OAuthCallbackHandler)
    if use_https:
        cert_path, key_path = ensure_localhost_cert(cert_dir or Path("credentials"))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
        server.socket = context.wrap_socket(server.socket, server_side=True)
        print(
            "Listening for OAuth callback on https://localhost:{port}/callback\n"
            "If the browser warns about the certificate, choose Advanced -> Continue to localhost.\n".format(
                port=port
            )
        )
    server.timeout = 1.0
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            server.handle_request()
            if _OAuthCallbackHandler.auth_code:
                return _OAuthCallbackHandler.auth_code
            if _OAuthCallbackHandler.auth_error:
                raise RuntimeError(f"OAuth error: {_OAuthCallbackHandler.auth_error}")
    finally:
        server.server_close()
    raise TimeoutError("Timed out waiting for OAuth callback")


def open_authorize_url(url: str) -> None:
    print(f"Open this URL if the browser does not launch:\n{url}\n")
    webbrowser.open(url)


def redirect_uri(port: int = 8765, *, secure: bool = False) -> str:
    if secure:
        return f"https://localhost:{port}/callback"
    return f"http://127.0.0.1:{port}/callback"
