#!/usr/bin/env python3
"""
Generate a Gmail OAuth refresh token for local/dev usage (loopback redirect).

Reads `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` from environment, or from
`backend/.env` if present.

Scopes requested:
- https://www.googleapis.com/auth/gmail.readonly
- https://www.googleapis.com/auth/gmail.send

Security note:
- This prints a refresh token. Treat it like a password.
"""

from __future__ import annotations

import os
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx


def _read_env_file_value(env_path: Path, key: str) -> str:
    try:
        raw = env_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    prefix = key + "="
    for line in raw:
        if not line or line.lstrip().startswith("#"):
            continue
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def _get_setting(key: str) -> str:
    val = (os.environ.get(key) or "").strip()
    if val:
        return val
    env_path = Path(__file__).resolve().parents[1] / "backend" / ".env"
    if env_path.exists():
        return _read_env_file_value(env_path, key)
    return ""


class _OAuthHandler(BaseHTTPRequestHandler):
    server_version = "OpenWorldOAuth/1.0"
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/oauth2callback":
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        code = (qs.get("code") or [""])[0].strip()
        err = (qs.get("error") or [""])[0].strip()

        if err:
            self.server.auth_error = err  # type: ignore[attr-defined]
        if code:
            self.server.auth_code = code  # type: ignore[attr-defined]

        body = (
            "OK. You can close this tab and return to the terminal.\n"
            if code
            else "Authorization failed. Return to the terminal.\n"
        )
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:  # quiet
        return


def main() -> int:
    client_id = _get_setting("GMAIL_CLIENT_ID")
    client_secret = _get_setting("GMAIL_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("Missing Gmail OAuth client credentials.")
        print("Expected non-empty values for: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET")
        print("You can set them in environment or in backend/.env")
        return 2

    redirect_host = "127.0.0.1"
    redirect_port = 53682
    redirect_uri = f"http://{redirect_host}:{redirect_port}/oauth2callback"

    scopes = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
    ]

    auth_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
        auth_params, quote_via=urllib.parse.quote
    )

    httpd = HTTPServer((redirect_host, redirect_port), _OAuthHandler)
    httpd.auth_code = ""  # type: ignore[attr-defined]
    httpd.auth_error = ""  # type: ignore[attr-defined]

    def _serve() -> None:
        # single request then exit
        httpd.handle_request()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()

    print("1) Browser will open for Google authorization.")
    print(f"2) Approve access; you'll be redirected to {redirect_uri}")
    print("3) Return here; refresh token will be printed.")
    print("")
    webbrowser.open(auth_url)
    print("If the browser didn't open, copy/paste this URL:")
    print(auth_url)
    print("")

    t.join(timeout=300)
    code = getattr(httpd, "auth_code", "") or ""
    err = getattr(httpd, "auth_error", "") or ""
    if not code:
        print(f"No authorization code received. error={err!r}".strip())
        return 1

    token_payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    with httpx.Client(timeout=30) as c:
        resp = c.post("https://oauth2.googleapis.com/token", data=token_payload)
        resp.raise_for_status()
        data = resp.json()

    refresh_token = (data.get("refresh_token") or "").strip()
    access_token = (data.get("access_token") or "").strip()
    if not refresh_token:
        print("No refresh_token returned. Common causes:")
        print("- You previously authorized without prompt=consent for this client")
        print("- The OAuth consent screen is misconfigured (test users)")
        print("- Wrong client type (use Desktop app)")
        if access_token:
            print("An access_token was returned, but it won't survive restarts.")
        return 1

    # Optional sanity check: ensure gmail.send is present in tokeninfo scopes.
    scopes_ok = None
    try:
        info = httpx.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"access_token": access_token},
            timeout=20,
        )
        if info.status_code == 200:
            got = (info.json().get("scope") or "").split()
            scopes_ok = "https://www.googleapis.com/auth/gmail.send" in set(got)
    except Exception:
        scopes_ok = None

    print("")
    print("Refresh token generated. Keep it secret.")
    print("")
    print(f"GMAIL_REFRESH_TOKEN={refresh_token}")
    if scopes_ok is True:
        print("Scope check: gmail.send OK")
    elif scopes_ok is False:
        print("Scope check: gmail.send MISSING (re-authorize with correct scopes)")
    else:
        print("Scope check: skipped (could not verify)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

