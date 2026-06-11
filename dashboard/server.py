import importlib.util
import json
import os
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATE_DIR = os.environ.get("AGENT_STATE_DIR", os.path.join("dashboard", "state"))
AGENTS_DIR = os.path.join(STATE_DIR, "agents")
EVENTS_PATH = os.path.join(STATE_DIR, "events.jsonl")
THREADS_DIR = os.path.join(STATE_DIR, "threads")
IMPORTANT_PATH = os.path.join(STATE_DIR, "important.json")
MODELS_PATH = os.path.join(STATE_DIR, "models.json")
ALLOWED_MODELS = ("haiku", "sonnet", "opus")
INDEX_PATH = os.path.join(HERE, "index.html")
PORT = int(os.environ.get("DASHBOARD_PORT", "8787"))

ORDER = ["orchestrator", "researcher", "business_ops", "claude_code"]


def _rank(name: str) -> int:
    return ORDER.index(name) if name in ORDER else len(ORDER)


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(name)) or "agent"


def _new_conv_id() -> str:
    return uuid.uuid4().hex[:8]


# ── agent records ──────────────────────────────────────────────────────────────

def read_models() -> dict:
    if not os.path.isfile(MODELS_PATH):
        return {}
    try:
        with open(MODELS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_model(agent: str, model: str) -> None:
    models = read_models()
    models[agent] = model
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(MODELS_PATH, "w", encoding="utf-8") as f:
        json.dump(models, f)


def read_agents() -> list:
    if not os.path.isdir(AGENTS_DIR):
        return []
    agents = []
    for entry in os.listdir(AGENTS_DIR):
        if not entry.endswith(".json"):
            continue
        try:
            with open(os.path.join(AGENTS_DIR, entry), encoding="utf-8") as f:
                agents.append(json.load(f))
        except (OSError, json.JSONDecodeError):
            continue
    agents.sort(key=lambda a: (_rank(a.get("name", "")), a.get("name", "")))
    models = read_models()
    for a in agents:
        a["model"] = models.get(a.get("name", ""), a.get("model") or "sonnet")
    return agents


# ── events ─────────────────────────────────────────────────────────────────────

def read_events(limit: int = 40) -> list:
    if not os.path.isfile(EVENTS_PATH):
        return []
    try:
        with open(EVENTS_PATH, encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
    except OSError:
        return []
    events = []
    for line in lines[-limit:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    events.reverse()
    return events


# ── conversations ──────────────────────────────────────────────────────────────

def conv_dir(agent: str) -> str:
    return os.path.join(THREADS_DIR, _safe(agent))


def conv_index_path(agent: str) -> str:
    return os.path.join(conv_dir(agent), "index.json")


def conv_thread_path(agent: str, conv_id: str) -> str:
    return os.path.join(conv_dir(agent), f"{conv_id}.jsonl")


def _legacy_thread_path(agent: str) -> str:
    return os.path.join(THREADS_DIR, f"{_safe(agent)}.jsonl")


def _read_jsonl(path: str, limit: int = 200) -> list:
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
    except OSError:
        return []
    messages = []
    for line in lines[-limit:]:
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return messages


def _write_index(agent: str, convs: list) -> None:
    dir_ = conv_dir(agent)
    os.makedirs(dir_, exist_ok=True)
    tmp = conv_index_path(agent) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(convs, f)
    os.replace(tmp, conv_index_path(agent))


def read_conversations(agent: str) -> list:
    path = conv_index_path(agent)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def get_or_create_conv(agent: str) -> dict:
    """Return active conv, bootstrapping from legacy flat file on first call."""
    convs = read_conversations(agent)
    if convs:
        for c in convs:
            if c.get("active"):
                return c
        return convs[0]
    # First time: create default conv, migrating legacy flat file if present
    conv_id = _new_conv_id()
    now = datetime.now().isoformat(timespec="seconds")
    conv = {"id": conv_id, "title": "Chat 1", "created_at": now, "updated_at": now, "active": True}
    os.makedirs(conv_dir(agent), exist_ok=True)
    legacy = _legacy_thread_path(agent)
    if os.path.isfile(legacy):
        import shutil
        shutil.copy2(legacy, conv_thread_path(agent, conv_id))
        for m in _read_jsonl(conv_thread_path(agent, conv_id)):
            if m.get("from") == "user" and (m.get("text") or "").strip():
                conv["title"] = m["text"].strip()[:50]
                break
    _write_index(agent, [conv])
    return conv


def create_conversation(agent: str) -> dict:
    convs = read_conversations(agent)
    for c in convs:
        c["active"] = False
    conv_id = _new_conv_id()
    now = datetime.now().isoformat(timespec="seconds")
    conv = {"id": conv_id, "title": "New Chat", "created_at": now, "updated_at": now, "active": True}
    convs.insert(0, conv)
    _write_index(agent, convs)
    return conv


def activate_conversation(agent: str, conv_id: str) -> dict | None:
    convs = read_conversations(agent)
    target = None
    for c in convs:
        c["active"] = c["id"] == conv_id
        if c["id"] == conv_id:
            target = c
    if target:
        _write_index(agent, convs)
    return target


def read_thread(agent: str, conv_id: str = None, limit: int = 200) -> list:
    if conv_id:
        return _read_jsonl(conv_thread_path(agent, conv_id), limit)
    conv = get_or_create_conv(agent)
    return _read_jsonl(conv_thread_path(agent, conv["id"]), limit)


def append_message(agent: str, sender: str, text: str, extra: dict = None, conv_id: str = None) -> dict:
    if not conv_id:
        conv = get_or_create_conv(agent)
        conv_id = conv["id"]
    os.makedirs(conv_dir(agent), exist_ok=True)
    message = {"ts": datetime.now().isoformat(timespec="seconds"), "from": sender, "text": text}
    if extra:
        message.update(extra)
    with open(conv_thread_path(agent, conv_id), "a", encoding="utf-8") as f:
        f.write(json.dumps(message) + "\n")
    # Keep legacy flat file updated so inotifywait watchers still fire
    os.makedirs(THREADS_DIR, exist_ok=True)
    try:
        with open(_legacy_thread_path(agent), "a", encoding="utf-8") as lf:
            lf.write(json.dumps(message) + "\n")
    except OSError:
        pass
    # Update index: timestamp + auto-title from first real user message
    convs = read_conversations(agent)
    for c in convs:
        if c["id"] == conv_id:
            c["updated_at"] = message["ts"]
            if c["title"] in ("New Chat", "Chat 1") and sender == "user" and text.strip():
                c["title"] = text.strip()[:50]
            break
    if convs:
        _write_index(agent, convs)
    return message


# Legacy alias so external callers that use thread_path() still work
def thread_path(agent: str) -> str:
    return _legacy_thread_path(agent)


# ── cost / analytics ───────────────────────────────────────────────────────────

def _load_cost_module():
    path = os.path.join(ROOT, "cost-monitor", "cost_monitor.py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location("cost_monitor", path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    return module


def cost_summary():
    module = _load_cost_module()
    if module is None:
        return None
    records = list(module.read_records(module.LOG_PATH))
    today = datetime.now().date().isoformat()
    tier = module.select_tier(records)
    total = module.today_total(records, today, tier) if records else 0.0
    status = module.status_for(total, module.DAILY_BUDGET_USD, module.WARN_RATIO)
    return {"today": round(total, 2), "budget": module.DAILY_BUDGET_USD, "status": status}


def build_analytics() -> dict:
    import datetime as _dt
    path = os.environ.get("COST_LOG_PATH", "")
    today = _dt.datetime.now().date().isoformat()
    week_ago = (_dt.datetime.now().date() - _dt.timedelta(days=7)).isoformat()
    month = today[:7]
    periods = {"today": {"cost": 0.0, "tokens": 0}, "week": {"cost": 0.0, "tokens": 0}, "month": {"cost": 0.0, "tokens": 0}}
    by_source = {}
    if path and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = (record.get("timestamp", "") or "")[:10]
                    cost = record.get("estimated_cost_usd") or 0
                    tokens = record.get("total_tokens") or 0
                    source = record.get("source", "other") or "other"
                    if ts == today:
                        periods["today"]["cost"] += cost
                        periods["today"]["tokens"] += tokens
                        entry = by_source.setdefault(source, {"cost": 0.0, "tokens": 0})
                        entry["cost"] += cost
                        entry["tokens"] += tokens
                    if ts >= week_ago:
                        periods["week"]["cost"] += cost
                        periods["week"]["tokens"] += tokens
                    if ts[:7] == month:
                        periods["month"]["cost"] += cost
                        periods["month"]["tokens"] += tokens
        except OSError:
            pass
    sources = sorted(
        [{"source": s, "cost": round(v["cost"], 2), "tokens": v["tokens"]} for s, v in by_source.items()],
        key=lambda x: -x["cost"],
    )
    activity = {}
    for event in read_events(2000):
        if (event.get("ts", "") or "")[:10] == today:
            a = activity.setdefault(event.get("name", "?"), {"events": 0, "done": 0})
            a["events"] += 1
            if event.get("status") == "done":
                a["done"] += 1
    acts = sorted([{"name": n, **v} for n, v in activity.items()], key=lambda x: -x["events"])
    for p in periods.values():
        p["cost"] = round(p["cost"], 2)
    return {"periods": periods, "by_source": sources, "activity": acts}


def read_important():
    if not os.path.isfile(IMPORTANT_PATH):
        return None
    try:
        with open(IMPORTANT_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def build_state() -> dict:
    return {
        "agents": read_agents(),
        "events": read_events(),
        "cost": cost_summary(),
        "important": read_important(),
        "now": datetime.now().isoformat(timespec="seconds"),
    }


# ── HTTP handler ───────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/api/agents":
            self._json(build_state())
            return

        if parsed.path == "/api/agent":
            name = (params.get("agent") or [""])[0]
            conv_id = (params.get("conv_id") or [None])[0]
            if not name:
                self._json({"error": "agent required"}, 400)
                return
            record = next((a for a in read_agents() if a.get("name") == name), None)
            events = [e for e in read_events(500) if e.get("name") == name][:80]
            conv = get_or_create_conv(name)
            active_id = conv_id or conv["id"]
            thread = read_thread(name, active_id)
            self._json({"agent": record, "events": events, "thread": thread, "conv_id": active_id})
            return

        if parsed.path == "/api/conversations":
            name = (params.get("agent") or [""])[0]
            if not name:
                self._json({"error": "agent required"}, 400)
                return
            get_or_create_conv(name)  # ensure at least one exists
            self._json({"agent": name, "conversations": read_conversations(name)})
            return

        if parsed.path == "/api/analytics":
            self._json(build_analytics())
            return

        if parsed.path in ("/", "/index.html"):
            self._file(INDEX_PATH, "text/html; charset=utf-8")
            return

        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/conversations":
            payload = self._read_json()
            agent = (payload.get("agent") or "").strip()
            if not agent:
                self._json({"error": "agent required"}, 400)
                return
            conv = create_conversation(agent)
            self._json({"ok": True, "conversation": conv})
            return

        if path == "/api/activate":
            payload = self._read_json()
            agent = (payload.get("agent") or "").strip()
            conv_id = (payload.get("conv_id") or "").strip()
            if not agent or not conv_id:
                self._json({"error": "agent and conv_id required"}, 400)
                return
            conv = activate_conversation(agent, conv_id)
            if not conv:
                self._json({"error": "conversation not found"}, 404)
                return
            self._json({"ok": True, "conversation": conv})
            return

        if path == "/api/message":
            payload = self._read_json()
            agent = (payload.get("agent") or "").strip()
            text = (payload.get("text") or "").strip()
            conv_id = (payload.get("conv_id") or "").strip() or None
            if not agent or not text:
                self._json({"error": "agent and text required"}, 400)
                return
            message = append_message(agent, "user", text[:4000], conv_id=conv_id)
            self._json({"ok": True, "message": message})
            return

        if path == "/api/model":
            payload = self._read_json()
            agent = (payload.get("agent") or "").strip()
            model = (payload.get("model") or "").strip().lower()
            if not agent or model not in ALLOWED_MODELS:
                self._json({"error": "agent and valid model (haiku|sonnet|opus) required"}, 400)
                return
            write_model(agent, model)
            self._json({"ok": True, "agent": agent, "model": model})
            return

        if path == "/api/debug":
            payload = self._read_json()
            try:
                os.makedirs(STATE_DIR, exist_ok=True)
                with open(os.path.join(STATE_DIR, "debug.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), **payload}) + "\n")
            except OSError:
                pass
            self._json({"ok": True})
            return

        self.send_error(404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/conversations":
            payload = self._read_json()
            agent = (payload.get("agent") or "").strip()
            conv_id = (payload.get("conv_id") or "").strip()
            if not agent or not conv_id:
                self._json({"error": "agent and conv_id required"}, 400)
                return
            convs = read_conversations(agent)
            remaining = [c for c in convs if c["id"] != conv_id]
            if len(remaining) == len(convs):
                self._json({"error": "not found"}, 404)
                return
            deleted_was_active = any(c.get("active") and c["id"] == conv_id for c in convs)
            if deleted_was_active and remaining:
                remaining[0]["active"] = True
            _write_index(agent, remaining)
            try:
                os.remove(conv_thread_path(agent, conv_id))
            except OSError:
                pass
            new_active = next((c["id"] for c in remaining if c.get("active")), None)
            self._json({"ok": True, "new_active_conv_id": new_active})
            return
        self.send_error(404)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b""
            return json.loads(body or b"{}")
        except (ValueError, json.JSONDecodeError):
            return {}

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, content_type):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"dashboard on http://0.0.0.0:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
