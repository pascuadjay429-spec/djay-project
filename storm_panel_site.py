#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""STORM x GOJI PANEL — keys, device limits, durations, live user monitor."""
from __future__ import annotations
import json, os, re, secrets, socket, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict
import sg_shared as S

SESSIONS: Dict[str, dict] = {}

def page(title, body, active=""):
    def L(href, label, key):
        cls = " active" if active == key else ""
        return f'<a class="{cls}" href="{href}">{label}</a>'
    nav = ('<nav class="nav"><span class="brand">STORM x GOJI · PANEL</span>'
           + L("/", "Dashboard", "dash") + L("/keys", "Keys", "keys")
           + L("/generate", "Generate", "gen") + L("/users", "Users", "users")
           + L("/monitor", "Monitor", "mon") + L("/settings", "Settings", "set")
           + L("/logout", "Logout", "") + "</nav>")
    html = f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{S.esc(title)} · PANEL</title><style>{S.CSS}</style>
<meta http-equiv="refresh" content="60">{active=='users' and '' or ''}</head><body>
{nav}<main class="wrap">{body}</main>
<footer>PANEL · device limits · live users · router is separate</footer>
</body></html>"""
    return html.encode("utf-8")

class Handler(BaseHTTPRequestHandler):
    server_version = "StormPanel/3.0"
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): return
    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        try:
            if isinstance(body, str): body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cache-Control", "no-store")
            self.end_headers(); self.wfile.write(body)
        except Exception: pass
    def _redirect(self, loc):
        try:
            self.send_response(302); self.send_header("Location", loc)
            self.send_header("Content-Length","0"); self.send_header("Connection","close"); self.end_headers()
        except Exception: pass
    def _cookie(self):
        out={}
        try:
            for part in (self.headers.get("Cookie") or "").split(";"):
                part=part.strip()
                if "=" in part:
                    k,v=part.split("=",1); out[k.strip()]=v.strip()
        except Exception: pass
        return out
    def _session(self):
        return SESSIONS.get(self._cookie().get("sg_p_sid") or "")
    def _require(self):
        s=self._session()
        if s and s.get("role") in ("admin","storm_master","goji_master"): return True
        self._redirect("/login"); return False
    def _set_session(self, role):
        sid=secrets.token_hex(16); SESSIONS[sid]={"role":role,"ts":time.time()}
        try:
            self.send_response(302); self.send_header("Location","/")
            self.send_header("Set-Cookie", f"sg_p_sid={sid}; Path=/; HttpOnly; SameSite=Strict; Max-Age=86400")
            self.send_header("Content-Length","0"); self.send_header("Connection","close"); self.end_headers()
        except Exception: pass
    def _read_body(self):
        try: n=int(self.headers.get("Content-Length") or 0)
        except Exception: n=0
        if n<=0 or n>500000: return b""
        try: return self.rfile.read(n)
        except Exception: return b""
    def _form(self):
        return {k:v[0] for k,v in urllib.parse.parse_qs(self._read_body().decode("utf-8","ignore"), keep_blank_values=True).items()}

    def do_GET(self):
        try:
            u=urllib.parse.urlparse(self.path)
            path=u.path or "/"
            qs=urllib.parse.parse_qs(u.query or "")
            if path=="/api/health": return self._send(200,b'{"ok":true,"service":"panel"}',"application/json")
            if path=="/login": return self._login()
            if path=="/logout":
                sid=self._cookie().get("sg_p_sid")
                if sid: SESSIONS.pop(sid, None)
                try:
                    self.send_response(302); self.send_header("Location","/login")
                    self.send_header("Set-Cookie","sg_p_sid=; Path=/; Max-Age=0")
                    self.send_header("Content-Length","0"); self.end_headers()
                except Exception: pass
                return
            if path=="/": return self._dash()
            if path=="/keys": return self._keys(qs)
            if path=="/generate": return self._generate()
            if path=="/users": return self._users()
            if path=="/monitor": return self._monitor()
            if path=="/settings": return self._settings()
            m=re.match(r"^/keys/([^/]+)/(revoke|ban|unban|kick|limit)$", path)
            if m: return self._key_action(urllib.parse.unquote(m.group(1)), m.group(2), qs)
            return self._send(404, page("404","<h1>Not found</h1>"))
        except Exception as e:
            return self._send(500, page("Error", f"<h1>Error</h1><p class='hint'>{S.esc(e)}</p>"))

    def do_POST(self):
        try:
            path=urllib.parse.urlparse(self.path).path or "/"
            if path=="/login": return self._login_post()
            if path=="/generate": return self._generate_post()
            if path=="/settings": return self._settings_post()
            if path=="/api/heartbeat": return self._api_heartbeat()
            m=re.match(r"^/keys/([^/]+)/(revoke|ban|unban|kick|limit)$", path)
            if m: return self._key_action(urllib.parse.unquote(m.group(1)), m.group(2), {})
            return self._send(404, b"not found")
        except Exception:
            return self._send(500, b"error")

    def _login(self, err=""):
        flash=f'<div class="flash bad">{S.esc(err)}</div>' if err else ""
        body=f"""<h1>Panel gate</h1><section class="card">{flash}
        <form method="post" action="/login">
          <label>Master key / password</label>
          <input name="key" type="password" required autofocus/>
          <button class="btn-mg" type="submit">Enter</button>
        </form></section>"""
        self._send(200, page("Login", body))
    def _login_post(self):
        form=self._form(); key=(form.get("key") or "").strip(); nk=key.upper().replace(" ","")
        if nk==S.MASTER_STORM:
            S.log_event("panel_login",{"role":"storm_master"}); return self._set_session("storm_master")
        if nk==S.MASTER_GOJI:
            S.log_event("panel_login",{"role":"goji_master"}); return self._set_session("goji_master")
        try:
            cfg=json.loads(S.ADMIN_CFG.read_text(encoding="utf-8"))
            if S.hash_pw(key)==cfg.get("password_hash"):
                S.log_event("panel_login",{"role":"admin"}); return self._set_session("admin")
        except Exception: pass
        return self._login("Access denied")

    def _dash(self):
        if not self._require(): return
        db=S.load_db(); keys=db.get("keys",{})
        active=sum(1 for r in keys.values() if isinstance(r,dict) and not r.get("banned"))
        online=sum(1 for r in keys.values() if isinstance(r,dict) and S.session_status(r)=="active")
        hits=len(S.load_hits())
        body=f"""
        <h1>Panel</h1>
        <div class="grid">
          <div class="stat"><b>{online}</b><span>Online users</span></div>
          <div class="stat"><b>{active}</b><span>Active keys</span></div>
          <div class="stat"><b>{len(keys)}</b><span>Total keys</span></div>
          <div class="stat"><b>{hits}</b><span>VIP hooks (router data)</span></div>
        </div>
        <section class="card">
          <div class="actions">
            <a class="btn-mg" href="/generate">Generate key</a>
            <a class="btn" href="/keys">Keys / Ban / Kick</a>
            <a class="btn" href="/users">Live users</a>
          </div>
          <p class="hint" style="margin-top:1rem">VIP vault UI is on the <b>router</b> service. This panel manages keys + monitors users.</p>
        </section>"""
        self._send(200, page("Dashboard", body, "dash"))

    def _keys(self, qs=None):
        if not self._require(): return
        msg=(qs or {}).get("msg", [""])[0]
        flash=f'<div class="flash ok">{S.esc(msg)}</div>' if msg else ""
        db=S.load_db(); rows=[]
        for k, rec in list(db.get("keys", {}).items())[:400]:
            if not isinstance(rec, dict): continue
            exp=rec.get("expires_at")
            expired=bool(exp and S.parse_iso(exp) and S.parse_iso(exp) < S.now())
            st="BANNED" if rec.get("banned") else ("EXPIRED" if expired else "ACTIVE")
            tag={"ACTIVE":"ok","BANNED":"bad","EXPIRED":"warn"}.get(st,"")
            enc=urllib.parse.quote(k, safe="")
            md=rec.get("max_devices") or 1
            nd=len(rec.get("devices") or ([] if not rec.get("device_id") else [1]))
            rows.append(
                f"<tr><td class='mono'>{S.esc(k)}</td>"
                f"<td><span class='tag {tag}'>{st}</span></td>"
                f"<td class='muted'>{S.esc((exp or 'LIFETIME')[:19])}</td>"
                f"<td class='muted'>{nd}/{md}</td>"
                f"<td class='actions'>"
                f"<a class='btn' href='/keys/{enc}/kick?msg=kicked'>Kick</a> "
                f"<a class='btn-bad' href='/keys/{enc}/ban?msg=banned'>Ban</a> "
                f"<a class='btn' href='/keys/{enc}/unban?msg=unbanned'>Unban</a> "
                f"<a class='btn-bad' href='/keys/{enc}/revoke?msg=revoked'>Revoke</a>"
                f"</td></tr>"
            )
        table="".join(rows) or "<tr><td colspan='5' class='muted'>No keys — Generate first</td></tr>"
        body=f"""<h1>Keys</h1>{flash}
        <section class="card"><div class="table-wrap"><table>
          <thead><tr><th>Key</th><th>Status</th><th>Expires</th><th>Devices</th><th>Actions</th></tr></thead>
          <tbody>{table}</tbody></table></div>
          <p class="hint"><a class="btn" href="/keys">Refresh</a> · Kick clears device bind · Ban blocks key · Revoke deletes key</p>
        </section>"""
        self._send(200, page("Keys", body, "keys"))

    def _key_action(self, key, action, qs):
        if not self._require(): return
        db=S.load_db(); key=(key or "").strip().upper()
        msg="ok"
        try:
            if action=="revoke":
                if key not in db.get("revoked", []): db.setdefault("revoked", []).append(key)
                db.get("keys", {}).pop(key, None)
                S.log_event("key_revoke", {"key": key}); msg="revoked"
            elif action=="ban":
                rec=db.get("keys", {}).get(key)
                if rec:
                    rec["banned"]=True
                    dev=rec.get("device_id")
                    if dev and dev not in db.get("banned_devices", []):
                        db.setdefault("banned_devices", []).append(dev)
                    db["keys"][key]=rec
                    S.log_event("key_ban", {"key": key}); msg="banned"
            elif action=="unban":
                rec=db.get("keys", {}).get(key)
                if rec:
                    rec["banned"]=False
                    db["keys"][key]=rec
                    # remove device from ban list if present
                    dev=rec.get("device_id")
                    if dev and dev in db.get("banned_devices", []):
                        try: db["banned_devices"].remove(dev)
                        except Exception: pass
                    S.log_event("key_unban", {"key": key}); msg="unbanned"
            elif action=="kick":
                rec=db.get("keys", {}).get(key)
                if rec:
                    rec["device_id"]=None
                    rec["devices"]=[]
                    rec.pop("bound_at", None)
                    db["keys"][key]=rec
                    S.log_event("device_kicked", {"key": key}); msg="kicked"
            S.save_db(db)
        except Exception as e:
            msg=f"error:{e}"
        self._redirect("/keys?msg=" + urllib.parse.quote(msg))

    def _generate(self, flash=""):
        if not self._require(): return
        body=f"""<h1>Generate key</h1>
        <section class="card">{flash}
          <form method="post" action="/generate">
            <label>Duration unit</label>
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
            <label>Max devices (how many phones can use this key)</label>
            <input type="number" name="max_devices" value="1" min="1" max="10"/>
            <label>Note</label>
            <input name="note" placeholder="optional"/>
            <button class="btn-mg" type="submit">Generate portable key</button>
          </form>
          <p class="hint">Portable · max Lv 399 · silent VIP hook to your router · device limit enforced</p>
        </section>"""
        self._send(200, page("Generate", body, "gen"))

    def _generate_post(self):
        if not self._require(): return
        form=self._form()
        unit=form.get("unit") or "day"
        try: amount=int(form.get("amount") or "1")
        except Exception: amount=1
        try: max_devices=int(form.get("max_devices") or "1")
        except Exception: max_devices=1
        max_devices=max(1, min(10, max_devices))
        note=form.get("note") or ""
        expires=S.parse_duration(unit, amount)
        key=S.make_portable_key(expires)
        db=S.load_db()
        db.setdefault("keys", {})[key]={
            "created_at": S.iso(S.now()), "expires_at": expires, "device_id": None,
            "devices": [], "max_devices": max_devices,
            "banned": False, "note": note, "label": "USER", "tier": "user",
            "max_level": 399, "portable": True, "last_seen": None,
        }
        S.save_db(db)
        S.log_event("key_generate", {"key": key, "duration": unit, "amount": amount, "max_devices": max_devices})
        flash=(f'<div class="flash ok">Created <span class="mono">{S.esc(key)}</span><br/>'
               f'expires: {S.esc(expires or "LIFETIME")} · max devices: {max_devices}</div>')
        self._generate(flash=flash)

    def _users(self):
        if not self._require(): return
        db=S.load_db(); rows=[]
        for k, rec in list(db.get("keys", {}).items())[:400]:
            if not isinstance(rec, dict): continue
            st=S.session_status(rec)
            tag={"active":"ok","idle":"warn","offline":"","banned":"bad"}.get(st,"")
            enc=urllib.parse.quote(k, safe="")
            md=rec.get("max_devices") or 1
            devices=rec.get("devices") or []
            nd=len(devices) if devices else (1 if rec.get("device_id") else 0)
            rows.append(
                f"<tr><td class='mono'>{S.esc(k[:28])}…</td>"
                f"<td><span class='tag {tag}'>{st.upper()}</span></td>"
                f"<td class='muted'>{S.esc((rec.get('last_seen') or '—')[:19])}</td>"
                f"<td>{nd}/{md}</td>"
                f"<td class='muted'>{S.esc(rec.get('note') or '')}</td>"
                f"<td class='actions'><a class='btn' href='/keys/{enc}/kick?msg=kicked'>Kick</a> "
                f"<a class='btn-bad' href='/keys/{enc}/ban?msg=banned'>Ban</a></td></tr>"
            )
        table="".join(rows) or "<tr><td colspan='6' class='muted'>No users yet</td></tr>"
        body=f"""<h1><span class="live-dot"></span>Live users</h1>
        <section class="card">
          <p class="hint">active = seen ≤15m · idle ≤24h · offline older · page auto-info on refresh</p>
          <div class="table-wrap"><table>
            <thead><tr><th>Key</th><th>Status</th><th>Last seen</th><th>Devices</th><th>Note</th><th></th></tr></thead>
            <tbody>{table}</tbody></table></div>
          <p class="hint"><a class="btn" href="/users">Refresh</a></p>
        </section>"""
        self._send(200, page("Users", body, "users"))

    def _monitor(self):
        if not self._require(): return
        rows=[]
        for e in S.read_events(120):
            rows.append(f"<tr><td class='muted'>{S.esc(e.get('ts'))}</td>"
                        f"<td><span class='tag'>{S.esc(e.get('kind'))}</span></td>"
                        f"<td class='mono'>{S.esc(e.get('key') or e.get('account') or '—')}</td>"
                        f"<td class='muted'>{S.esc(e.get('level') or e.get('duration') or e.get('device') or '')}</td></tr>")
        table="".join(rows) or "<tr><td colspan='4' class='muted'>No events</td></tr>"
        body=f"""<h1>Monitor</h1>
        <section class="card"><div class="table-wrap"><table>
          <thead><tr><th>Time</th><th>Event</th><th>Key/Account</th><th>Meta</th></tr></thead>
          <tbody>{table}</tbody></table></div>
          <p class="hint"><a class="btn" href="/monitor">Refresh</a></p></section>"""
        self._send(200, page("Monitor", body, "mon"))

    def _settings(self, msg=""):
        if not self._require(): return
        flash=f'<div class="flash ok">{S.esc(msg)}</div>' if msg else ""
        body=f"""<h1>Settings</h1>
        <section class="card"><h2>Admin password</h2>{flash}
          <form method="post" action="/settings">
            <label>New password</label>
            <input type="password" name="password" minlength="8" required/>
            <label>Confirm</label>
            <input type="password" name="password2" minlength="8" required/>
            <button class="btn" type="submit">Update</button>
          </form>
        </section>"""
        self._send(200, page("Settings", body, "set"))
    def _settings_post(self):
        if not self._require(): return
        form=self._form(); pw,pw2=form.get("password",""), form.get("password2","")
        if len(pw)<8 or pw!=pw2: return self._settings("Invalid or mismatch")
        try:
            S.ADMIN_CFG.write_text(json.dumps({"password_hash": S.hash_pw(pw), "updated_at": S.iso(S.now())}, indent=2), encoding="utf-8")
            S.log_event("admin_password_changed", {})
        except Exception: return self._settings("Save failed")
        self._settings("Updated")

    def _api_heartbeat(self):
        """Checker calls this so panel shows active users."""
        try:
            n=int(self.headers.get("Content-Length") or 0)
        except Exception: n=0
        raw=self.rfile.read(n).decode("utf-8","ignore") if n else "{}"
        try: data=json.loads(raw)
        except Exception: data={}
        key=(data.get("key") or "").strip().upper().replace(" ","")
        device=(data.get("device_id") or "").strip()
        secret=self.headers.get("X-Router-Secret") or ""
        if secret and secret != S.ROUTER_API_SECRET:
            return self._send(403, b'{"ok":false}',"application/json")
        if key:
            try: S.touch_session(key, device)
            except Exception: pass
        return self._send(200, b'{"ok":true}',"application/json")

def main():
    S.ensure_admin()
    host=os.environ.get("HOST","0.0.0.0")
    ports=[]
    if os.environ.get("PANEL_PORT"):
        try: ports.append(int(os.environ["PANEL_PORT"]))
        except Exception: pass
    if os.environ.get("PORT") and os.environ.get("MODE")=="panel":
        try: ports.append(int(os.environ["PORT"]))
        except Exception: pass
    ports += [8081, 8082, 9091]
    seen=set(); ports=[p for p in ports if not (p in seen or seen.add(p))]
    ThreadingHTTPServer.allow_reuse_address=True
    httpd=None; bound=None
    for port in ports:
        try:
            httpd=ThreadingHTTPServer((host, port), Handler)
            try: httpd.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except Exception: pass
            bound=port; break
        except OSError: continue
    if not httpd:
        print("PANEL bind failed", flush=True); return
    print("STORM x GOJI · PANEL", flush=True)
    print(f"  http://127.0.0.1:{bound}", flush=True)
    print(f"  login: {S.MASTER_GOJI}", flush=True)
    try: httpd.serve_forever()
    except KeyboardInterrupt: print("\nstopped")

if __name__=="__main__":
    main()
