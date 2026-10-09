"""Replica minima di Supabase per i test locali del sito.

- /auth/v1/*  login con email e password di prova, emette JWT firmati come Supabase
- /rest/v1/*  inoltrato a PostgREST (stesso motore che Supabase usa davanti a Postgres)

Uso: python fake_supabase.py  (variabili: POSTGREST_URL, POSTGREST_JWT_SECRET, PORT)
Solo per test: NON usare in produzione.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

POSTGREST = os.getenv("POSTGREST_URL", "http://localhost:3000")
SECRET = os.getenv("POSTGREST_JWT_SECRET", "segreto-di-prova-lungo-almeno-32-caratteri!!")
PORT = int(os.getenv("PORT", "8787"))
USERS = {"io@example.org": "prova-123", "intruso@example.org": "prova-123"}


def jwt(claims: dict) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    head, body = enc({"alg": "HS256", "typ": "JWT"}), enc(claims)
    sig = hmac.new(SECRET.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{base64.urlsafe_b64encode(sig).rstrip(b'=').decode()}"


def user_obj(email: str) -> dict:
    uid = "00000000-0000-4000-8000-" + hashlib.md5(email.encode()).hexdigest()[:12]
    return {"id": uid, "aud": "authenticated", "role": "authenticated", "email": email,
            "app_metadata": {"provider": "email"}, "user_metadata": {}, "created_at": "2026-10-01T00:00:00Z"}


def session_for(email: str) -> dict:
    now = int(time.time())
    u = user_obj(email)
    token = jwt({"aud": "authenticated", "role": "authenticated", "email": email, "sub": u["id"], "exp": now + 3600})
    return {"access_token": token, "token_type": "bearer", "expires_in": 3600, "expires_at": now + 3600,
            "refresh_token": base64.urlsafe_b64encode(email.encode()).decode(), "user": u}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Expose-Headers", "Content-Range, Content-Location, Preference-Applied")

    def _json(self, code: int, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _auth(self, method: str):
        parts = urlsplit(self.path)
        if parts.path == "/auth/v1/token":
            grant = parse_qs(parts.query).get("grant_type", [""])[0]
            body = json.loads(self._body() or b"{}")
            if grant == "password":
                email = body.get("email", "").lower()
                if USERS.get(email) == body.get("password"):
                    return self._json(200, session_for(email))
                return self._json(400, {"error": "invalid_grant", "error_description": "Invalid login credentials",
                                        "code": 400, "msg": "Invalid login credentials"})
            if grant == "refresh_token":
                email = base64.urlsafe_b64decode(body.get("refresh_token", "") + "==").decode()
                return self._json(200, session_for(email))
        if parts.path == "/auth/v1/user":
            auth = self.headers.get("Authorization", "")
            try:
                payload = json.loads(base64.urlsafe_b64decode(auth.split(".")[1] + "=="))
                return self._json(200, user_obj(payload["email"]))
            except Exception:
                return self._json(401, {"msg": "not authenticated"})
        if parts.path == "/auth/v1/logout":
            self.send_response(204)
            self._cors()
            self.end_headers()
            return
        return self._json(404, {"msg": "not found"})

    def _proxy(self, method: str):
        url = POSTGREST + self.path[len("/rest/v1"):]
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() in {"authorization", "prefer", "content-type", "accept", "range", "range-unit",
                                    "accept-profile", "content-profile"}}
        if "authorization" not in {k.lower() for k in headers} and self.headers.get("apikey"):
            headers["Authorization"] = "Bearer " + self.headers["apikey"]
        body = self._body() if method in ("POST", "PATCH", "PUT", "DELETE") else None
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            resp = urllib.request.urlopen(req)
            code, rh, data = resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            code, rh, data = e.code, e.headers, e.read()
        self.send_response(code)
        self._cors()
        for k in ("Content-Type", "Content-Range", "Preference-Applied"):
            if rh.get(k):
                self.send_header(k, rh[k])
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _route(self, method):
        if self.path.startswith("/auth/v1/"):
            return self._auth(method)
        if self.path.startswith("/rest/v1/"):
            return self._proxy(method)
        return self._json(404, {"msg": "not found"})

    def do_GET(self): self._route("GET")
    def do_POST(self): self._route("POST")
    def do_PATCH(self): self._route("PATCH")
    def do_PUT(self): self._route("PUT")
    def do_DELETE(self): self._route("DELETE")
    def do_HEAD(self): self._route("HEAD")


if __name__ == "__main__":
    print(f"Supabase di prova su http://localhost:{PORT}")
    print("ANON_KEY=" + jwt({"role": "anon", "exp": int(time.time()) + 86400 * 30}))
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
