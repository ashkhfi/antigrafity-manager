#!/usr/bin/env python3
"""
agm-web — Antigravity Manager Web Dashboard
Fully standalone. Zero external dependencies.
No dependency on 9router.

Usage:
  agm-web                   Start on port 8877
  agm-web --port 3000       Custom port
  agm-web --import-9router  Import accounts from 9router DB on start
"""
import http.server, json, os, sys, time, hashlib, signal, textwrap
import sqlite3, threading, socketserver, traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# Config
DATA_DIR = Path.home() / ".agm"
DB_PATH = DATA_DIR / "accounts.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
USAGE_DB = DATA_DIR / "usage.db"
TOKEN_FILE = Path.home() / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
ROUTER_DB = Path.home() / ".9router" / "db" / "data.sqlite"  # legacy, optional

CLIENT_ID = os.environ.get("AGM_CLIENT_ID", "PLACEHOLDER_ID")
CLIENT_SECRET = os.environ.get("AGM_CLIENT_SECRET", "PLACEHOLDER_SECRET")
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
LOAD_CA_URL = "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"
SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs",
]
REDIRECT_URI = "http://localhost:18923/callback"
DB_VERSION = 3

HTML_PATH = Path(__file__).parent / "agm-dashboard.html"
HTML = HTML_PATH.read_text(encoding="utf-8") if HTML_PATH.exists() else "<h1>Dashboard HTML not found</h1>"


def init_usage_db():
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(USAGE_DB))
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS usage_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, email TEXT, model TEXT DEFAULT 'gemini-3-flash-agent', prompt_tokens INTEGER DEFAULT 0, completion_tokens INTEGER DEFAULT 0, cost REAL DEFAULT 0, status TEXT DEFAULT 'ok', error TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS usage_daily (date TEXT PRIMARY KEY, data TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS quota_errors (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, email TEXT, model TEXT, reset_time TEXT, message TEXT)")
    conn.commit()
    conn.close()


# Database using JSON file
class Database:
    def __init__(self, path=DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._data = self._load()

    def _load(self):
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text())
                if raw.get("version") != DB_VERSION:
                    raw = self._migrate(raw)
                return raw
            except (json.JSONDecodeError, OSError):
                bak = self.path.with_suffix(".json.corrupt")
                try:
                    self.path.rename(bak)
                except:
                    pass
        return self._empty()

    def _empty(self):
        return {"version": DB_VERSION, "accounts": [], "current_email": ""}

    def _migrate(self, old):
        data = self._empty()
        if "accounts" in old:
            for acc in old["accounts"]:
                acc.setdefault("id", self._gen_id(acc.get("email", "")))
                data["accounts"].append(acc)
        self._save(data)
        return data

    def _save(self, data=None):
        if data is None:
            data = self._data
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        tmp.rename(self.path)

    def _now(self):
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    def _gen_id(self, email):
        return hashlib.md5(email.encode()).hexdigest()[:12]

    def list_accounts(self, provider="antigravity"):
        with self._lock:
            return [a for a in self._data["accounts"] if a.get("provider") == provider]

    def get_account(self, account_id):
        with self._lock:
            for a in self._data["accounts"]:
                if a.get("id") == account_id:
                    return a
        return None

    def get_account_by_email(self, email):
        with self._lock:
            for a in self._data["accounts"]:
                if a.get("email") == email:
                    return a
        return None

    def find_by_token(self, refresh_token, access_token=""):
        """Match token file to account in JSON DB."""
        with self._lock:
            for a in self._data["accounts"]:
                if a.get("refresh_token") and a["refresh_token"] == refresh_token:
                    return a
                if access_token and a.get("access_token") and len(access_token) >= 50 and len(a["access_token"]) >= 50:
                    if access_token[:50] == a["access_token"][:50]:
                        return a
        return None

    def add_account(self, account):
        with self._lock:
            existing = None
            for a in self._data["accounts"]:
                if a.get("email") == account.get("email"):
                    existing = a
                    break
            if existing:
                existing.update({k: v for k, v in account.items() if v is not None})
                existing["updated_at"] = self._now()
                self._save()
                return existing, False
            account["id"] = self._gen_id(account.get("email", str(time.time())))
            account.setdefault("created_at", self._now())
            account.setdefault("updated_at", self._now())
            self._data["accounts"].append(account)
            self._save()
            return account, True

    def update_account(self, account_id, updates):
        with self._lock:
            acc = self.get_account(account_id)
            if not acc:
                return None
            acc.update(updates)
            acc["updated_at"] = self._now()
            self._save()
            return acc

    def delete_account(self, account_id):
        with self._lock:
            before = len(self._data["accounts"])
            self._data["accounts"] = [a for a in self._data["accounts"] if a.get("id") != account_id]
            if len(self._data["accounts"]) < before:
                self._save()
                return True
            return False

    def toggle_active(self, account_id):
        acc = self.get_account(account_id)
        if not acc:
            return None
        return self.update_account(account_id, {"is_active": not acc.get("is_active", True)})

    def set_current(self, email):
        self._data["current_email"] = email
        self._save()

    def get_current(self):
        return self._data.get("current_email", "")

    def stats(self):
        accounts = self.list_accounts()
        active = sum(1 for a in accounts if a.get("is_active", True))
        now = datetime.now(timezone.utc)
        healthy = expiring = expired = 0
        for a in accounts:
            exp = a.get("expires_at")
            if not exp:
                continue
            try:
                exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                diff = (exp_dt - now).total_seconds()
                if diff > 600:
                    healthy += 1
                elif diff > 0:
                    expiring += 1
                else:
                    expired += 1
            except:
                pass
        test_counts = {}
        for a in accounts:
            ts = a.get("test_status", "unknown")
            test_counts[ts] = test_counts.get(ts, 0) + 1
        return {
            "total": len(accounts),
            "active": active,
            "inactive": len(accounts) - active,
            "healthy": healthy,
            "expiring": expiring,
            "expired": expired,
            "test_status": test_counts,
        }

    def get_active_tokens(self):
        accounts = self.list_accounts()
        return sorted(
            [a for a in accounts if a.get("is_active", True) and a.get("access_token")],
            key=lambda a: a.get("priority", 99),
        )

    # Legacy: import from 9router (optional)
    def sync_from_9router(self):
        if not ROUTER_DB.exists():
            return 0, "No 9router DB (standalone mode)"
        try:
            conn = sqlite3.connect(str(ROUTER_DB))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id,email,name,priority,isActive,data,createdAt,updatedAt FROM providerConnections WHERE provider='antigravity'"
            ).fetchall()
            conn.close()
        except Exception as e:
            return 0, f"9router error: {e}"
        count = 0
        for row in rows:
            d = json.loads(row["data"])
            self.add_account({
                "email": row["email"] or "",
                "name": row["name"] or row["email"] or "",
                "provider": "antigravity",
                "is_active": bool(row["isActive"]),
                "priority": row["priority"] or 99,
                "access_token": d.get("accessToken", ""),
                "refresh_token": d.get("refreshToken", ""),
                "expires_at": d.get("expiresAt", ""),
                "scope": d.get("scope", ""),
                "project_id": d.get("projectId", ""),
                "test_status": d.get("testStatus", "unknown"),
                "error_code": d.get("errorCode"),
                "last_error": d.get("lastError"),
                "last_used_at": d.get("lastUsedAt"),
                "router_id": row["id"],
                "created_at": row["createdAt"],
                "updated_at": row["updatedAt"],
            })
            count += 1
        return count, f"Imported {count} accounts from 9router"

    def import_usage_from_9router(self):
        """One-time import of usage data from 9router SQLite."""
        if not ROUTER_DB.exists():
            return 0, "No 9router DB"
        try:
            conn = sqlite3.connect(str(ROUTER_DB))
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT dateKey, data FROM usageDaily").fetchall()
            errs = conn.execute(
                "SELECT timestamp, connectionId, status, data FROM requestDetails WHERE status='error' ORDER BY timestamp DESC LIMIT 50"
            ).fetchall()
            conn.close()
        except Exception as e:
            return 0, str(e)

        # Import daily usage
        local = sqlite3.connect(str(USAGE_DB))
        imported = 0
        for row in rows:
            local.execute("INSERT OR REPLACE INTO usage_daily (date, data) VALUES (?, ?)", (row["dateKey"], row["data"]))
            imported += 1

        # Map connectionId to email for quota errors
        accts = self.list_accounts()
        conn_map = {}
        for a in accts:
            rid = a.get("router_id", "")
            if rid:
                conn_map[rid] = a.get("email", rid)

        for row in errs:
            d = json.loads(row["data"])
            resp = d.get("response", {})
            if isinstance(resp, dict):
                err_obj = resp.get("error", resp)
                if isinstance(err_obj, str):
                    try:
                        err_obj = json.loads(err_obj)
                    except:
                        pass
                if isinstance(err_obj, dict):
                    inner = err_obj.get("error", {})
                    if isinstance(inner, dict):
                        for det in inner.get("details", []):
                            meta = det.get("metadata", {})
                            if meta.get("quotaResetTimeStamp"):
                                email = conn_map.get(row["connectionId"], row["connectionId"][:12] if row["connectionId"] else "?")
                                local.execute(
                                    "INSERT INTO quota_errors (ts, email, model, reset_time, message) VALUES (?, ?, ?, ?, ?)",
                                    (
                                        row["timestamp"],
                                        email,
                                        meta.get("model", "?"),
                                        meta["quotaResetTimeStamp"],
                                        inner.get("message", "")[:200],
                                    ),
                                )
        local.commit()
        local.close()
        return imported, f"Imported {imported} daily records, {len(errs)} errors from 9router"


# Settings
class Settings:
    DEFAULTS = {
        "fallback_strategy": "round_robin",
        "consecutive_use_count": 1,
        "auto_rotate": True,
        "max_backups": 5,
        "port": 8877,
        "theme": "dark",
    }

    def __init__(self, path=SETTINGS_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self):
        if self.path.exists():
            try:
                return {**self.DEFAULTS, **json.loads(self.path.read_text())}
            except (json.JSONDecodeError, OSError):
                pass
        return dict(self.DEFAULTS)

    def get(self):
        return dict(self._data)

    def update(self, updates):
        self._data.update(updates)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))
        tmp.rename(self.path)

    def __getitem__(self, key):
        return self._data.get(key)


# OAuth helpers
def build_auth_url():
    return AUTH_URL + "?" + urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    })


def exchange_code(code):
    body = urlencode({
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()
    req = Request(TOKEN_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urlopen(req) as r:
        return json.loads(r.read())


def refresh_token_api(refresh_tok):
    body = urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_tok,
        "grant_type": "refresh_token",
    }).encode()
    req = Request(TOKEN_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urlopen(req) as r:
        return json.loads(r.read())


def get_user_info(access_token):
    req = Request("https://openidconnect.googleapis.com/v1/userinfo")
    req.add_header("Authorization", f"Bearer {access_token}")
    with urlopen(req) as r:
        return json.loads(r.read())


def load_code_assist(access_token, project_id=""):
    req = Request(LOAD_CA_URL, method="POST")
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Content-Type", "application/json")
    body = json.dumps({"cloudProjectId": project_id, "deviceId": "agm-web", "machineId": "agm-web"}).encode()
    with urlopen(req, data=body) as r:
        return json.loads(r.read())


# API functions (standalone — no 9router dependency)
def get_active_account_info(db):
    """Get info about which account agy is currently using, using JSON DB."""
    if not TOKEN_FILE.exists():
        # Fallback: use current_email from DB
        cur = db.get_current()
        if cur:
            a = db.get_account_by_email(cur)
            if a:
                return {"active": True, "email": cur, "project_id": a.get("project_id", "?"), "expired": False, "expiry": "", "token_masked": "via-switch"}
        return {"active": False, "email": cur or "(none)"}
    try:
        with open(TOKEN_FILE) as f:
            tok = json.load(f)
        rt = tok.get("token", {}).get("refresh_token", "")
        at = tok.get("token", {}).get("access_token", "")
        exp = tok.get("token", {}).get("expiry", "")

        # Find account in JSON DB
        account = db.find_by_token(rt, at)
        email = account["email"] if account else "(unknown)"

        # Check expiry
        now = datetime.now(timezone.utc)
        expired = True
        if exp:
            try:
                exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                expired = exp_dt < now
            except:
                pass

        return {
            "active": True,
            "account": account,
            "email": email,
            "project_id": account.get("project_id", "?") if account else "?",
            "expired": expired,
            "expiry": exp,
            "token_masked": f"{at[:12]}...{at[-6:]}" if len(at) > 18 else at,
        }
    except Exception as e:
        return {"active": False, "error": str(e)}


def switch_account(email, db):
    """Switch agy to use a specific account by email. Uses JSON DB only."""
    token_file = TOKEN_FILE
    # Find account in JSON DB
    target = None
    for a in db.list_accounts():
        if a.get("email") == email:
            target = a
            break

    if not target:
        return {"ok": False, "error": f"Account '{email}' not found in DB"}

    if not target.get("refresh_token") and not target.get("access_token"):
        return {"ok": False, "error": f"Account '{email}' has no tokens"}

    payload = {
        "token": {
            "access_token": target.get("access_token", ""),
            "token_type": "Bearer",
            "refresh_token": target.get("refresh_token", ""),
            "expiry": target.get("expires_at", ""),
        },
        "auth_method": "consumer",
    }
    os.makedirs(os.path.dirname(str(token_file)), exist_ok=True)
    with open(token_file, "w") as f:
        json.dump(payload, f)

    # Also set current in DB
    db.set_current(email)

    return {
        "ok": True,
        "message": f"Switched to {email}",
        "email": email,
        "project_id": target.get("project_id", "?"),
    }


def get_usage_stats(db):
    """Get usage statistics from JSON DB (token health)."""
    accounts = db.list_accounts()
    now = datetime.now(timezone.utc)
    healthy = expiring = expired = no_token = 0
    per_account = []
    active_info = get_active_account_info(db)
    active_email = active_info.get("email", "")

    for a in accounts:
        exp = a.get("expires_at", "")
        status = "no_token"
        hours_left = None
        if exp:
            try:
                exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                diff = (exp_dt - now).total_seconds() / 3600
                hours_left = round(diff, 1)
                if diff > 24:
                    status = "healthy"
                    healthy += 1
                elif diff > 0:
                    status = "expiring"
                    expiring += 1
                else:
                    status = "expired"
                    expired += 1
            except:
                no_token += 1
        else:
            no_token += 1

        per_account.append({
            "email": a.get("email", "?"),
            "is_active": a.get("is_active", True),
            "test_status": a.get("test_status", "unknown"),
            "token_status": status,
            "hours_left": hours_left,
            "is_current": a.get("email") == active_email,
            "priority": a.get("priority", 99),
            "last_error": a.get("last_error"),
            "error_code": a.get("error_code"),
        })

    per_account.sort(key=lambda x: (not x["is_current"], x["priority"]))
    return {
        "total": len(accounts),
        "active_count": sum(1 for a in accounts if a.get("is_active", True)),
        "token_health": {"healthy": healthy, "expiring": expiring, "expired": expired, "no_token": no_token},
        "current_account": active_email,
        "accounts": per_account,
    }


def get_quota_data(db):
    """Get quota/usage data from local usage.db."""
    import sqlite3
    result = {"daily": [], "totals": {}, "by_account": {}, "by_model": {}, "errors": [], "quota_limits": [], "reference": {}}

    local = sqlite3.connect(str(USAGE_DB))
    local.row_factory = sqlite3.Row

    try:
        # Read daily usage
        rows = local.execute("SELECT date, data FROM usage_daily ORDER BY date DESC LIMIT 7").fetchall()
        for row in rows:
            d = json.loads(row["data"])
            result["daily"].append({
                "date": row["date"],
                "requests": d.get("requests", 0),
                "prompt_tokens": d.get("promptTokens", 0),
                "completion_tokens": d.get("completionTokens", 0),
                "cost": round(d.get("cost", 0), 4),
                "cached_tokens": d.get("cachedTokens", 0),
                "by_model": d.get("byModel", {}),
                "by_account": d.get("byAccount", {}),
            })

        # Aggregate
        total_req = total_pt = total_ct = total_cost = 0
        agg_by_model = {}
        agg_by_account = {}
        for day in result["daily"]:
            total_req += day["requests"]
            total_pt += day["prompt_tokens"]
            total_ct += day["completion_tokens"]
            total_cost += day["cost"]
            for mk, mv in day.get("by_model", {}).items():
                if mk not in agg_by_model:
                    agg_by_model[mk] = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0}
                agg_by_model[mk]["requests"] += mv.get("requests", 0)
                agg_by_model[mk]["prompt_tokens"] += mv.get("promptTokens", 0)
                agg_by_model[mk]["completion_tokens"] += mv.get("completionTokens", 0)
                agg_by_model[mk]["cost"] += mv.get("cost", 0)
            for ak, av in day.get("by_account", {}).items():
                if ak not in agg_by_account:
                    agg_by_account[ak] = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0}
                agg_by_account[ak]["requests"] += av.get("requests", 0)
                agg_by_account[ak]["prompt_tokens"] += av.get("promptTokens", 0)
                agg_by_account[ak]["completion_tokens"] += av.get("completionTokens", 0)
                agg_by_account[ak]["cost"] += av.get("cost", 0)

        result["totals"] = {
            "requests": total_req,
            "prompt_tokens": total_pt,
            "completion_tokens": total_ct,
            "cost": round(total_cost, 4),
        }

        # By model
        sorted_models = sorted(agg_by_model.items(), key=lambda x: -x[1]["cost"])
        result["by_model"] = [{"model": k, **v, "cost": round(v["cost"], 4)} for k, v in sorted_models]

        # By account - map ids to emails
        accts = db.list_accounts()
        conn_map = {}
        for a in accts:
            rid = a.get("router_id", "")
            if rid:
                conn_map[rid] = a.get("email", rid)
        sorted_accounts = sorted(agg_by_account.items(), key=lambda x: -x[1]["cost"])
        result["by_account"] = [
            {"connection_id": k, "email": conn_map.get(k, k[:12] + "..."), **v, "cost": round(v["cost"], 4)}
            for k, v in sorted_accounts
        ]

        # Quota errors from local DB
        errs = local.execute(
            "SELECT ts, email, model, reset_time, message FROM quota_errors ORDER BY ts DESC LIMIT 10"
        ).fetchall()
        for row in errs:
            result["errors"].append({
                "timestamp": row["ts"],
                "email": row["email"],
                "message": row["message"],
            })

        # Quota limits
        max_req = max((v["requests"] for v in agg_by_account.values()), default=1) or 1
        max_pt = max((v["prompt_tokens"] for v in agg_by_account.values()), default=1) or 1

        quota_limits = []
        for cid, av in agg_by_account.items():
            usage_pct = round(max(av["requests"] / max_req * 100, av["prompt_tokens"] / max_pt * 100), 1)
            quota_limits.append({
                "connection_id": cid,
                "email": conn_map.get(cid, cid[:12] + "..."),
                "requests": av["requests"],
                "prompt_tokens": av["prompt_tokens"],
                "completion_tokens": av["completion_tokens"],
                "cost": round(av["cost"], 4),
                "usage_pct": usage_pct,
                "is_exhausted": False,
                "hours_until_reset": None,
                "model": "",
                "error_message": "",
            })
        quota_limits.sort(key=lambda x: -x["usage_pct"])
        result["quota_limits"] = quota_limits
        result["reference"] = {"max_requests": max_req, "max_prompt_tokens": max_pt}

    except Exception as e:
        result["error"] = str(e)

    local.close()

    # Clean rounding
    for m in result.get("by_model", []):
        m["cost"] = round(m["cost"], 4)
    for a in result.get("by_account", []):
        a["cost"] = round(a["cost"], 4)
    for q in result.get("quota_limits", []):
        q["cost"] = round(q["cost"], 4)
    result["totals"]["cost"] = round(result["totals"].get("cost", 0), 4)
    return result


# HTTP Handler
class Handler(http.server.BaseHTTPRequestHandler):
    db = Database()
    settings = Settings()

    def log_message(self, fmt, *args):
        pass  # Silence request logs

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, content):
        body = content.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/":
            return self._html(HTML)

        if path == "/api/accounts":
            accs = self.db.list_accounts()
            # Expose safe fields
            safe = []
            for a in accs:
                safe.append({
                    "id": a.get("id"),
                    "email": a.get("email"),
                    "name": a.get("name"),
                    "is_active": a.get("is_active", True),
                    "priority": a.get("priority", 99),
                    "project_id": a.get("project_id"),
                    "test_status": a.get("test_status"),
                    "expires_at": a.get("expires_at"),
                    "last_error": a.get("last_error"),
                    "error_code": a.get("error_code"),
                    "scope": a.get("scope"),
                    "created_at": a.get("created_at"),
                    "updated_at": a.get("updated_at"),
                })
            return self._json(safe)

        if path.startswith("/api/accounts/"):
            acc_id = path.split("/")[-1]
            acc = self.db.get_account(acc_id)
            if acc:
                return self._json(acc)
            return self._json({"error": "Not found"}, 404)

        if path == "/api/stats":
            return self._json(self.db.stats())

        if path == "/api/settings":
            return self._json(self.settings.get())

        if path == "/api/oauth-url":
            return self._json({"url": build_auth_url()})

        if path == "/api/active-account":
            return self._json(get_active_account_info(self.db))

        if path == "/api/usage":
            return self._json(get_usage_stats(self.db))

        if path == "/api/quota":
            return self._json(get_quota_data(self.db))

        self._json({"error": "Not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/accounts":
            body = self._read_body()
            code = body.get("code", "")
            if not code:
                return self._json({"ok": False, "error": "Code required"}, 400)
            try:
                if code.startswith("http"):
                    qs = parse_qs(urlparse(code).query)
                    if "code" in qs:
                        code = qs["code"][0]

                token_data = exchange_code(code)
                access_token = token_data.get("access_token", "")
                refresh_token_val = token_data.get("refresh_token", "")
                expires_in = token_data.get("expires_in", 3600)
                expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

                email = ""
                name = ""
                try:
                    ui = get_user_info(access_token)
                    email = ui.get("email", "")
                    name = ui.get("name", email)
                except:
                    pass

                project_id = ""
                try:
                    ca = load_code_assist(access_token)
                    project_id = ca.get("cloudaicompanion", {}).get("project", "")
                except:
                    pass

                account = {
                    "email": email,
                    "name": name,
                    "provider": "antigravity",
                    "is_active": True,
                    "access_token": access_token,
                    "refresh_token": refresh_token_val,
                    "expires_at": expires_at,
                    "scope": " ".join(SCOPES),
                    "project_id": project_id,
                    "test_status": "active",
                }
                acc, is_new = self.db.add_account(account)
                action = "added" if is_new else "updated"
                return self._json({"ok": True, "message": f"{email} {action}. Project: {project_id}"})
            except HTTPError as e:
                body_text = ""
                try:
                    body_text = e.read().decode()[:200]
                except:
                    pass
                return self._json({"ok": False, "error": f"HTTP {e.code}: {body_text}"}, 400)
            except Exception as e:
                return self._json({"ok": False, "error": str(e)[:200]}, 400)

        if path == "/api/settings":
            body = self._read_body()
            self.settings.update(body)
            return self._json({"ok": True, "message": "Settings saved"})

        if path == "/api/refresh-all":
            accounts = self.db.list_accounts()
            results = []
            for a in accounts:
                email = a.get("email", "?")
                rt = a.get("refresh_token", "")
                if not rt:
                    results.append({"email": email, "ok": False, "message": "No refresh token"})
                    continue
                try:
                    tok = refresh_token_api(rt)
                    new_at = tok.get("access_token", "")
                    if new_at:
                        new_expires = datetime.now(timezone.utc) + timedelta(seconds=tok.get("expires_in", 3600))
                        self.db.update_account(a["id"], {
                            "access_token": new_at,
                            "expires_at": new_expires.isoformat(),
                            "test_status": "active",
                        })
                        results.append({"email": email, "ok": True, "message": "Refreshed"})
                    else:
                        self.db.update_account(a["id"], {"test_status": "unavailable", "last_error": "Refresh failed"})
                        results.append({"email": email, "ok": False, "message": "Refresh returned no token"})
                except HTTPError as e:
                    self.db.update_account(a["id"], {"test_status": "unavailable", "last_error": f"HTTP {e.code}"})
                    results.append({"email": email, "ok": False, "message": f"HTTP {e.code}"})
                except Exception as e:
                    results.append({"email": email, "ok": False, "message": str(e)[:50]})
            return self._json({"ok": True, "results": results})

        if path == "/api/switch-account":
            body = self._read_body()
            email = body.get("email", "")
            if not email:
                return self._json({"ok": False, "error": "Email required"}, 400)
            return self._json(switch_account(email, self.db))

        self._json({"error": "Not found"}, 404)


class ReusableServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True


def main():
    port = 8877
    open_browser = False
    import_from_9router = False

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        elif args[i] == "--open":
            open_browser = True
            i += 1
        elif args[i] == "--import-9router":
            import_from_9router = True
            i += 1
        elif args[i] in ("--help", "-h"):
            print(textwrap.dedent(f"""                agm-web — Antigravity Manager Web Dashboard
                Fully standalone. Zero external dependencies.

                Usage:
                  agm-web                   Start on port {port}
                  agm-web --port 3000       Custom port
                  agm-web --open            Open browser
                  agm-web --import-9router  Import from 9router DB
            """))
            return
        else:
            i += 1

    # Init local usage DB
    init_usage_db()

    # Sync accounts (optionally from 9router)
    db = Database()
    if import_from_9router:
        count, msg = db.sync_from_9router()
        if count > 0:
            print(f"  {msg}")
        c2, msg2 = db.import_usage_from_9router()
        if c2 > 0:
            print(f"  {msg2}")

    # If no accounts exist, show message
    if len(db.list_accounts()) == 0:
        print("  No accounts yet. Add one via the dashboard or use --import-9router.")

    server = ReusableServer(("0.0.0.0", port), Handler)
    url = f"http://localhost:{port}"
    print()
    print(f"  \u26a1 AGM Web Dashboard (standalone)")
    print(f"  -> {url}")
    print(f"  -> Ctrl+C to stop")
    print()

    if open_browser:
        try:
            import webbrowser
            threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        except:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        server.server_close()


if __name__ == "__main__":
    main()
