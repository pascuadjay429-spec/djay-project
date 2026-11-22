#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STORM × GOJI — UNIFIED SITE
Vault (400-450) + Key panel (generate / kick / ban / revoke / users) + APIs
One process · one port · Render-ready
"""
from __future__ import annotations

import hmac
import json
import os
import random
import secrets
import socket
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional

import sg_shared as S

SESSIONS: Dict[str, dict] = {}


def page(title: str, body: str, active: str = "") -> bytes:
    def L(href: str, label: str, key: str) -> str:
        cls = " active" if active == key else ""
        return f'<a class="{cls}" href="{href}">{label}</a>'

    nav = (
        '<nav class="nav"><span class="brand">STORM × GOJI</span>'
        + L("/", "Vault", "vault")
        + L("/keys", "Keys", "keys")
        + L("/generate", "Generate", "gen")
        + L("/users", "Users", "users")
        + L("/monitor", "Monitor", "mon")
        + L("/logout", "Logout", "")
        + "</nav>"
    )
    html = f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{S.esc(title)} · STORM</title><style>{S.CSS}</style></head><body>
{nav}<main class="wrap">{body}</main>
<footer>UNIFIED · vault + key panel · one host</footer>
</body></html>"""
    return html.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "StormUnified/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        return

    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        try:
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cache-Control", "no-store")
            if extra:
                for k, v in extra.items():
                    self.send_header(k, str(v))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            pass

    def _redirect(self, loc: str):
        try:
            self.send_response(302)
            self.send_header("Location", loc)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
        except Exception:
            pass

    def _cookie(self) -> dict:
        out = {}
        try:
            for part in (self.headers.get("Cookie") or "").split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    out[k.strip()] = v.strip()
        except Exception:
            pass
        return out

    def _session(self) -> Optional[dict]:
        return SESSIONS.get(self._cookie().get("sg_sid") or "")

    def _require(self) -> bool:
        s = self._session()
        if s and s.get("role") in ("admin", "storm_master", "goji_master"):
            return True
        self._redirect("/login")
        return False

    def _set_session(self, role: str):
        sid = secrets.token_hex(16)
        SESSIONS[sid] = {"role": role, "ts": time.time()}
        try:
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header(
                "Set-Cookie",
                f"sg_sid={sid}; Path=/; HttpOnly; SameSite=Strict; Max-Age=86400",
            )
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
        except Exception:
            pass

    def _body(self) -> bytes:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except Exception:
            n = 0
        if n <= 0 or n > 2_000_000:
            return b""
        try:
            return self.rfile.read(n)
        except Exception:
            return b""

    def _json(self) -> dict:
        try:
            d = json.loads(self._body().decode("utf-8", "ignore") or "{}")
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def _form(self) -> dict:
        return {
            k: v[0]
            for k, v in urllib.parse.parse_qs(
                self._body().decode("utf-8", "ignore"), keep_blank_values=True
            ).items()
        }

    # ── GET ──────────────────────────────────────────────────────────
    def do_GET(self):
        try:
            u = urllib.parse.urlparse(self.path)
            path = u.path or "/"
            qs = urllib.parse.parse_qs(u.query or "")

            if path == "/api/health":
                return self._send(
                    200,
                    b'{"ok":true,"service":"storm-unified"}',
                    "application/json",
                )
            if path == "/login":
                return self._login()
            if path == "/logout":
                sid = self._cookie().get("sg_sid")
                if sid:
                    SESSIONS.pop(sid, None)
                try:
                    self.send_response(302)
                    self.send_header("Location", "/login")
                    self.send_header("Set-Cookie", "sg_sid=; Path=/; Max-Age=0")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                except Exception:
                    pass
                return

            if path in ("/", "/vault"):
                return self._vault(qs)
            if path == "/download":
                return self._download(qs, False)
            if path == "/download/random":
                return self._download(qs, True)
            if path == "/keys":
                return self._keys(qs)
            if path == "/generate":
                return self._generate()
            if path == "/users":
                return self._users()
            if path == "/monitor":
                return self._monitor()

            # key actions via GET (mobile-friendly)
            m = __import__("re").match(
                r"^/keys/([^/]+)/(revoke|ban|unban|kick)$", path
            )
            if m:
                return self._key_action(
                    urllib.parse.unquote(m.group(1)), m.group(2)
                )

            return self._send(404, page("404", "<h1>Not found</h1>"))
        except Exception as e:
            return self._send(
                500, page("Error", f"<h1>Error</h1><p class='hint'>{S.esc(e)}</p>")
            )

    # ── POST ─────────────────────────────────────────────────────────
    def do_POST(self):
        try:
            path = urllib.parse.urlparse(self.path).path or "/"
            if path == "/login":
                return self._login_post()
            if path == "/generate":
                return self._generate_post()
            if path == "/api/hook":
                return self._api_hook()
            if path == "/api/key/status":
                return self._api_key_status()
            if path == "/api/heartbeat":
                return self._api_heartbeat()
            m = __import__("re").match(
                r"^/keys/([^/]+)/(revoke|ban|unban|kick)$", path
            )
            if m:
                return self._key_action(
                    urllib.parse.unquote(m.group(1)), m.group(2)
                )
            return self._send(404, b'{"ok":false}', "application/json")
        except Exception:
            return self._send(500, b'{"ok":false}', "application/json")

    # ── auth ─────────────────────────────────────────────────────────
    def _login(self, err: str = ""):
        flash = f'<div class="flash bad">{S.esc(err)}</div>' if err else ""
        body = f"""<h1>Access</h1><section class="card">{flash}
        <p class="hint">Master key — vault + key panel</p>
        <form method="post" action="/login">
          <label>Master key</label>
          <input name="key" type="password" required autofocus autocomplete="current-password"/>
          <button class="btn-mg" type="submit">Enter</button>
        </form></section>"""
        self._send(200, page("Login", body))

    def _login_post(self):
        form = self._form()
        key = (form.get("key") or "").strip().upper().replace(" ", "")
        if key == S.MASTER_STORM:
            S.log_event("login", {"role": "storm_master"})
            return self._set_session("storm_master")
        if key == S.MASTER_GOJI:
            S.log_event("login", {"role": "goji_master"})
            return self._set_session("goji_master")
        try:
            cfg = json.loads(S.ADMIN_CFG.read_text(encoding="utf-8"))
            if S.hash_pw(form.get("key") or "") == cfg.get("password_hash"):
                S.log_event("login", {"role": "admin"})
                return self._set_session("admin")
        except Exception:
            pass
        return self._login("Access denied")

    # ── VAULT ────────────────────────────────────────────────────────
    def _vault(self, qs: dict):
        if not self._require():
            return
        hits = S.load_hits()
        total = len(hits)
        rows = []
        for h in hits[:300]:
            rows.append(
                "<tr>"
                f"<td class='mono'>{S.esc(h.get('account'))}</td>"
                f"<td><b style='color:var(--mg)'>{S.esc(h.get('codm_level'))}</b></td>"
                f"<td>{S.esc(h.get('codm_region') or '—')}</td>"
                f"<td>{S.esc(h.get('shell_balance') or 0)}</td>"
                f"<td class='muted'>{S.esc(str(h.get('hooked_at') or '')[:19])}</td>"
                f"<td class='muted'>{S.esc(h.get('hook_source') or '')}</td>"
                "</tr>"
            )
        table = (
            "".join(rows)
            or "<tr><td colspan='6' class='muted'>No VIP hooks yet</td></tr>"
        )
        dc = min(50, max(total, 1))
        body = f"""
        <h1><span class="live-dot"></span>VIP Vault <span class="tag">400–450</span></h1>
        <section class="card">
          <div class="grid">
            <div class="stat"><b>{total}</b><span>Elite hits</span></div>
            <div class="stat"><b>{min(300, total)}</b><span>Showing</span></div>
          </div>
          <h2>Download</h2>
          <form method="get" action="/download" style="display:flex;flex-wrap:wrap;gap:.7rem;align-items:end">
            <div style="flex:1;min-width:110px"><label>Count</label>
              <input type="number" name="count" min="1" value="{dc}"/></div>
            <div style="flex:1;min-width:110px"><label>Per VIP_part</label>
              <input type="number" name="per" min="1" max="500" value="50"/></div>
            <button class="btn-mg" type="submit">Download</button>
            <a class="btn" href="/download/random?count=25&per=50">Random 25</a>
            <a class="btn" href="/download?count={max(total,1)}&per=50">All</a>
          </form>
        </section>
        <section class="card">
          <div class="table-wrap"><table>
            <thead><tr><th>Account</th><th>Lv</th><th>Region</th><th>Shell</th><th>Hooked</th><th>Src</th></tr></thead>
            <tbody>{table}</tbody>
          </table></div>
          <p class="hint"><a class="btn" href="/">Refresh</a></p>
        </section>"""
        self._send(200, page("VIP Vault", body, "vault"))

    def _download(self, qs: dict, rnd: bool = False):
        if not self._require():
            return
        hits = S.load_hits()
        try:
            count = int((qs.get("count") or ["50"])[0])
        except Exception:
            count = 50
        try:
            per = int((qs.get("per") or ["50"])[0])
        except Exception:
            per = 50
        if not hits:
            return self._send(200, page("Empty", "<h1>No hits</h1>"))
        count = max(1, min(count, len(hits)))
        per = max(1, min(per, 500))
        selected = (
            random.sample(hits, min(count, len(hits))) if rnd else hits[:count]
        )
        parts = S.build_vip_parts(selected, per_file=per)
        if not parts:
            return self._send(200, page("Empty", "<h1>No hits</h1>"))
        if len(parts) == 1:
            name, content = parts[0]
            return self._send(
                200,
                content.encode("utf-8"),
                "text/plain; charset=utf-8",
                {"Content-Disposition": f'attachment; filename="{name}"'},
            )
        try:
            import io
            import zipfile

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for name, content in parts:
                    zf.writestr(name, content)
            return self._send(
                200,
                buf.getvalue(),
                "application/zip",
                {"Content-Disposition": 'attachment; filename="VIP_parts.zip"'},
            )
        except Exception:
            blob = "\n\n".join(f"##### {n} #####\n{c}" for n, c in parts)
            return self._send(
                200,
                blob.encode("utf-8"),
                "text/plain; charset=utf-8",
                {"Content-Disposition": 'attachment; filename="VIP_parts.txt"'},
            )

    # ── KEYS ─────────────────────────────────────────────────────────
    def _keys(self, qs: dict):
        if not self._require():
            return
        msg = (qs.get("msg") or [""])[0]
        flash = f'<div class="flash ok">{S.esc(msg)}</div>' if msg else ""
        db = S.load_db()
        rows = []
        for k, rec in list(db.get("keys", {}).items())[:400]:
            if not isinstance(rec, dict):
                continue
            exp = rec.get("expires_at")
            expired = bool(
                exp and S.parse_iso(exp) and S.parse_iso(exp) < S.now()
            )
            st = (
                "BANNED"
                if rec.get("banned")
                else ("EXPIRED" if expired else "ACTIVE")
            )
            tag = {"ACTIVE": "ok", "BANNED": "bad", "EXPIRED": "warn"}.get(st, "")
            enc = urllib.parse.quote(k, safe="")
            md = rec.get("max_devices") or 1
            devices = rec.get("devices") or []
            nd = len(devices) if devices else (1 if rec.get("device_id") else 0)
            rows.append(
                f"<tr><td class='mono'>{S.esc(k)}</td>"
                f"<td><span class='tag {tag}'>{st}</span></td>"
                f"<td class='muted'>{S.esc((exp or 'LIFETIME')[:19])}</td>"
                f"<td>{nd}/{md}</td>"
                f"<td class='actions'>"
                f"<a class='btn' href='/keys/{enc}/kick'>Kick</a> "
                f"<a class='btn-bad' href='/keys/{enc}/ban'>Ban</a> "
                f"<a class='btn' href='/keys/{enc}/unban'>Unban</a> "
                f"<a class='btn-bad' href='/keys/{enc}/revoke'>Revoke</a>"
                f"</td></tr>"
            )
        table = (
            "".join(rows)
            or "<tr><td colspan='5' class='muted'>No keys — Generate first</td></tr>"
        )
        body = f"""<h1>Keys</h1>{flash}
        <section class="card">
          <p class="hint"><a class="btn-mg" href="/generate">Generate</a> <a class="btn" href="/keys">Refresh</a></p>
          <div class="table-wrap"><table>
            <thead><tr><th>Key</th><th>Status</th><th>Expires</th><th>Devices</th><th>Actions</th></tr></thead>
            <tbody>{table}</tbody>
          </table></div>
        </section>"""
        self._send(200, page("Keys", body, "keys"))

    def _key_action(self, key: str, action: str):
        if not self._require():
            return
        db = S.load_db()
        key = (key or "").strip().upper()
        msg = "ok"
        try:
            if action == "revoke":
                if key not in db.get("revoked", []):
                    db.setdefault("revoked", []).append(key)
                db.get("keys", {}).pop(key, None)
                S.log_event("key_revoke", {"key": key})
                msg = "revoked"
            elif action == "ban":
                rec = db.get("keys", {}).get(key)
                if rec:
                    rec["banned"] = True
                    dev = rec.get("device_id")
                    if dev and dev not in db.get("banned_devices", []):
                        db.setdefault("banned_devices", []).append(dev)
                    db["keys"][key] = rec
                    S.log_event("key_ban", {"key": key})
                    msg = "banned"
            elif action == "unban":
                rec = db.get("keys", {}).get(key)
                if rec:
                    rec["banned"] = False
                    db["keys"][key] = rec
                    msg = "unbanned"
            elif action == "kick":
                rec = db.get("keys", {}).get(key)
                if rec:
                    rec["device_id"] = None
                    rec["devices"] = []
                    rec.pop("bound_at", None)
                    db["keys"][key] = rec
                    S.log_event("device_kicked", {"key": key})
                    msg = "kicked"
            S.save_db(db)
        except Exception as e:
            msg = f"err"
        self._redirect("/keys?msg=" + urllib.parse.quote(msg))

    def _generate(self, flash: str = ""):
        if not self._require():
            return
        body = f"""<h1>Generate key</h1>
        <section class="card">{flash}
          <form method="post" action="/generate">
            <label>Duration</label>
            <select name="unit">
              <option value="minute">minute</option>
              <option value="hour">hour</option>
              <option value="day" selected>day</option>
              <option value="week">week</option>
              <option value="month">month</option>
              <option value="year">year</option>
              <option value="lifetime">lifetime</option>
            </select>
            <label>Amount</label>
            <input type="number" name="amount" value="1" min="1"/>
            <label>Max devices</label>
            <input type="number" name="max_devices" value="1" min="1" max="10"/>
            <label>Note</label>
            <input name="note" placeholder="optional"/>
            <button class="btn-mg" type="submit">Generate</button>
          </form>
          <p class="hint">Portable · max Lv 399 · silent VIP hook to this vault</p>
        </section>"""
        self._send(200, page("Generate", body, "gen"))

    def _generate_post(self):
        if not self._require():
            return
        form = self._form()
        unit = form.get("unit") or "day"
        try:
            amount = int(form.get("amount") or "1")
        except Exception:
            amount = 1
        try:
            max_devices = int(form.get("max_devices") or "1")
        except Exception:
            max_devices = 1
        max_devices = max(1, min(10, max_devices))
        note = form.get("note") or ""
        expires = S.parse_duration(unit, amount)
        key = S.make_portable_key(expires)
        db = S.load_db()
        db.setdefault("keys", {})[key] = {
            "created_at": S.iso(S.now()),
            "expires_at": expires,
            "device_id": None,
            "devices": [],
            "max_devices": max_devices,
            "banned": False,
            "note": note,
            "label": "USER",
            "tier": "user",
            "max_level": 399,
            "portable": True,
            "last_seen": None,
        }
        S.save_db(db)
        S.log_event(
            "key_generate",
            {"key": key, "duration": unit, "amount": amount, "max_devices": max_devices},
        )
        flash = (
            f'<div class="flash ok">Created <span class="mono">{S.esc(key)}</span><br/>'
            f'{S.esc(expires or "LIFETIME")} · devices {max_devices}</div>'
        )
        self._generate(flash=flash)

    def _users(self):
        if not self._require():
            return
        db = S.load_db()
        rows = []
        for k, rec in list(db.get("keys", {}).items())[:400]:
            if not isinstance(rec, dict):
                continue
            st = S.session_status(rec)
            tag = {"active": "ok", "idle": "warn", "offline": "", "banned": "bad"}.get(
                st, ""
            )
            enc = urllib.parse.quote(k, safe="")
            md = rec.get("max_devices") or 1
            devices = rec.get("devices") or []
            nd = len(devices) if devices else (1 if rec.get("device_id") else 0)
            rows.append(
                f"<tr><td class='mono'>{S.esc(k[:28])}…</td>"
                f"<td><span class='tag {tag}'>{st.upper()}</span></td>"
                f"<td class='muted'>{S.esc((rec.get('last_seen') or '—')[:19])}</td>"
                f"<td>{nd}/{md}</td>"
                f"<td class='actions'><a class='btn' href='/keys/{enc}/kick'>Kick</a> "
                f"<a class='btn-bad' href='/keys/{enc}/ban'>Ban</a></td></tr>"
            )
        table = (
            "".join(rows)
            or "<tr><td colspan='5' class='muted'>No users</td></tr>"
        )
        body = f"""<h1><span class="live-dot"></span>Users</h1>
        <section class="card">
          <p class="hint">active ≤15m · idle ≤24h · offline older</p>
          <div class="table-wrap"><table>
            <thead><tr><th>Key</th><th>Status</th><th>Last seen</th><th>Devices</th><th></th></tr></thead>
            <tbody>{table}</tbody>
          </table></div>
          <p class="hint"><a class="btn" href="/users">Refresh</a></p>
        </section>"""
        self._send(200, page("Users", body, "users"))

    def _monitor(self):
        if not self._require():
            return
        rows = []
        for e in S.read_events(120):
            rows.append(
                f"<tr><td class='muted'>{S.esc(e.get('ts'))}</td>"
                f"<td><span class='tag'>{S.esc(e.get('kind'))}</span></td>"
                f"<td class='mono'>{S.esc(e.get('key') or e.get('account') or '—')}</td>"
                f"<td class='muted'>{S.esc(e.get('level') or e.get('duration') or e.get('reason') or '')}</td></tr>"
            )
        table = (
            "".join(rows)
            or "<tr><td colspan='4' class='muted'>No events</td></tr>"
        )
        body = f"""<h1>Monitor</h1>
        <section class="card"><div class="table-wrap"><table>
          <thead><tr><th>Time</th><th>Event</th><th>Key/Account</th><th>Meta</th></tr></thead>
          <tbody>{table}</tbody>
        </table></div>
        <p class="hint"><a class="btn" href="/monitor">Refresh</a></p></section>"""
        self._send(200, page("Monitor", body, "mon"))

    # ── APIs ─────────────────────────────────────────────────────────
    def _api_hook(self):
        secret = (
            self.headers.get("X-Router-Secret")
            or self.headers.get("x-router-secret")
            or ""
        )
        if not hmac.compare_digest(str(secret), str(S.ROUTER_API_SECRET)):
            return self._send(
                403, b'{"ok":false,"error":"forbidden"}', "application/json"
            )
        data = self._json()
        try:
            lvl = int(data.get("codm_level") or 0)
        except Exception:
            lvl = 0
        if lvl < 400 or lvl > 450:
            return self._send(
                200,
                b'{"ok":true,"stored":false,"reason":"out_of_band"}',
                "application/json",
            )
        if not data.get("account"):
            return self._send(400, b'{"ok":false}', "application/json")
        try:
            S.append_hit(data)
        except Exception:
            return self._send(500, b'{"ok":false}', "application/json")
        return self._send(200, b'{"ok":true,"stored":true}', "application/json")

    def _api_key_status(self):
        secret = (
            self.headers.get("X-Router-Secret")
            or self.headers.get("x-router-secret")
            or ""
        )
        if secret and not hmac.compare_digest(
            str(secret), str(S.ROUTER_API_SECRET)
        ):
            return self._send(403, b'{"ok":false}', "application/json")
        data = self._json()
        key = (data.get("key") or "").strip().upper().replace(" ", "")
        device = (data.get("device_id") or "").strip()
        if not key or key in (S.MASTER_STORM, S.MASTER_GOJI):
            return self._send(
                200, b'{"ok":true,"allowed":true}', "application/json"
            )
        db = S.load_db()
        if key in db.get("revoked", []):
            return self._send(
                200,
                b'{"ok":true,"allowed":false,"reason":"revoked"}',
                "application/json",
            )
        if device and device in db.get("banned_devices", []):
            return self._send(
                200,
                b'{"ok":true,"allowed":false,"reason":"device_banned"}',
                "application/json",
            )
        rec = db.get("keys", {}).get(key)
        if rec is None:
            return self._send(
                200, b'{"ok":true,"allowed":true}', "application/json"
            )
        if rec.get("banned"):
            return self._send(
                200,
                b'{"ok":true,"allowed":false,"reason":"banned"}',
                "application/json",
            )
        exp = rec.get("expires_at")
        if exp and S.parse_iso(exp) and S.parse_iso(exp) < S.now():
            return self._send(
                200,
                b'{"ok":true,"allowed":false,"reason":"expired"}',
                "application/json",
            )
        try:
            S.touch_session(key, device)
        except Exception:
            pass
        return self._send(200, b'{"ok":true,"allowed":true}', "application/json")

    def _api_heartbeat(self):
        data = self._json()
        key = (data.get("key") or "").strip().upper().replace(" ", "")
        device = (data.get("device_id") or "").strip()
        if key:
            try:
                S.touch_session(key, device)
            except Exception:
                pass
        return self._send(200, b'{"ok":true}', "application/json")


def main():
    S.ensure_admin()
    host = os.environ.get("HOST", "0.0.0.0")
    ports = []
    for k in ("PORT", "ROUTER_PORT", "PANEL_PORT"):
        if os.environ.get(k):
            try:
                ports.append(int(os.environ[k]))
            except Exception:
                pass
    ports += [8080, 8090, 8081, 8088]
    seen = set()
    ports = [p for p in ports if not (p in seen or seen.add(p))]
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = None
    bound = None
    for port in ports:
        try:
            httpd = ThreadingHTTPServer((host, port), Handler)
            try:
                httpd.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except Exception:
                pass
            bound = port
            break
        except OSError:
            continue
    if not httpd:
        print("bind failed", flush=True)
        return
    print("STORM × GOJI · UNIFIED (vault + keys)", flush=True)
    print(f"  http://0.0.0.0:{bound}", flush=True)
    print(f"  login: {S.MASTER_GOJI}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
