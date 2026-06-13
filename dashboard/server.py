import asyncio
import importlib.util
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATE_DIR = os.environ.get("AGENT_STATE_DIR", os.path.join("dashboard", "state"))
AGENTS_DIR = os.path.join(STATE_DIR, "agents")
EVENTS_PATH = os.path.join(STATE_DIR, "events.jsonl")
THREADS_DIR = os.path.join(STATE_DIR, "threads")
IMPORTANT_PATH = os.path.join(STATE_DIR, "important.json")
MODELS_PATH = os.path.join(STATE_DIR, "models.json")
ALLOWED_MODELS = ("haiku", "sonnet", "opus")
INDEX_PATH = os.path.join(HERE, "mission-control.dc.html")
SUPPORT_JS_PATH = os.path.join(HERE, "support.js")
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
    convs = read_conversations(agent)
    if convs:
        for c in convs:
            if c.get("active"):
                return c
        return convs[0]
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


def activate_conversation(agent: str, conv_id: str) -> Optional[dict]:
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
    os.makedirs(THREADS_DIR, exist_ok=True)
    try:
        with open(_legacy_thread_path(agent), "a", encoding="utf-8") as lf:
            lf.write(json.dumps(message) + "\n")
    except OSError:
        pass
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


# ── WebSocket connection manager ───────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self._conns: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._conns.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._conns:
            self._conns.remove(ws)

    async def broadcast(self, data: dict) -> None:
        dead = []
        for ws in self._conns:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


async def _state_broadcaster() -> None:
    last_sig = None
    while True:
        await asyncio.sleep(2)
        try:
            state = build_state()
            sig = json.dumps(
                [(a.get("name"), a.get("status"), a.get("task"), a.get("updated_at"))
                 for a in state.get("agents", [])]
            )
            if sig != last_sig:
                last_sig = sig
                await manager.broadcast(state)
        except Exception:
            pass


# ── app ────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_state_broadcaster())
    yield
    task.cancel()


app = FastAPI(title="Agent Mission Control", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── static files ───────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
@app.get("/mission-control.dc.html", include_in_schema=False)
def serve_index():
    return FileResponse(INDEX_PATH, media_type="text/html; charset=utf-8")


@app.get("/support.js", include_in_schema=False)
def serve_support():
    return FileResponse(SUPPORT_JS_PATH, media_type="application/javascript; charset=utf-8")


# ── WebSocket ──────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        await ws.send_json(build_state())
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ── REST: read ─────────────────────────────────────────────────────────────────

@app.get("/api/agents")
def get_agents():
    return build_state()


@app.get("/api/agent")
def get_agent(agent: str, conv_id: Optional[str] = None):
    record = next((a for a in read_agents() if a.get("name") == agent), None)
    events = [e for e in read_events(500) if e.get("name") == agent][:80]
    conv = get_or_create_conv(agent)
    active_id = conv_id or conv["id"]
    thread = read_thread(agent, active_id)
    return {"agent": record, "events": events, "thread": thread, "conv_id": active_id}


@app.get("/api/conversations")
def get_conversations(agent: str):
    get_or_create_conv(agent)
    return {"agent": agent, "conversations": read_conversations(agent)}


@app.get("/api/analytics")
def get_analytics():
    return build_analytics()


# ── REST: write ────────────────────────────────────────────────────────────────

class ConversationBody(BaseModel):
    agent: str


class ActivateBody(BaseModel):
    agent: str
    conv_id: str


class MessageBody(BaseModel):
    agent: str
    text: str
    conv_id: Optional[str] = None


class ModelBody(BaseModel):
    agent: str
    model: str


@app.post("/api/conversations")
def create_conv(body: ConversationBody):
    conv = create_conversation(body.agent)
    return {"ok": True, "conversation": conv}


@app.post("/api/activate")
def activate_conv(body: ActivateBody):
    conv = activate_conversation(body.agent, body.conv_id)
    if not conv:
        return JSONResponse({"error": "conversation not found"}, status_code=404)
    return {"ok": True, "conversation": conv}


@app.post("/api/message")
def post_message(body: MessageBody):
    message = append_message(body.agent, "user", body.text[:4000], conv_id=body.conv_id)
    return {"ok": True, "message": message}


@app.post("/api/model")
def set_model(body: ModelBody):
    if body.model not in ALLOWED_MODELS:
        return JSONResponse({"error": "model must be haiku, sonnet, or opus"}, status_code=400)
    write_model(body.agent, body.model)
    return {"ok": True, "agent": body.agent, "model": body.model}


@app.post("/api/debug")
async def post_debug(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(os.path.join(STATE_DIR, "debug.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), **body}) + "\n")
    except OSError:
        pass
    return {"ok": True}


@app.delete("/api/conversations")
async def delete_conv(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    agent = (body.get("agent") or "").strip()
    conv_id = (body.get("conv_id") or "").strip()
    if not agent or not conv_id:
        return JSONResponse({"error": "agent and conv_id required"}, status_code=400)
    convs = read_conversations(agent)
    remaining = [c for c in convs if c["id"] != conv_id]
    if len(remaining) == len(convs):
        return JSONResponse({"error": "not found"}, status_code=404)
    deleted_was_active = any(c.get("active") and c["id"] == conv_id for c in convs)
    if deleted_was_active and remaining:
        remaining[0]["active"] = True
    _write_index(agent, remaining)
    try:
        os.remove(conv_thread_path(agent, conv_id))
    except OSError:
        pass
    new_active = next((c["id"] for c in remaining if c.get("active")), None)
    return {"ok": True, "new_active_conv_id": new_active}


@app.post("/api/linkedin-analytics")
async def save_linkedin_analytics(request: Request):
    data = await request.json()
    path = os.path.join(STATE_DIR, "linkedin_analytics.json")
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return {"saved": True, "post_count": data.get("post_count", 0)}


@app.get("/api/log")
def get_log(agent: str, limit: int = 30):
    log_path = os.path.join(STATE_DIR, "logs", f"{agent}.jsonl")
    if not os.path.isfile(log_path):
        return {"agent": agent, "events": []}
    try:
        with open(log_path, encoding="utf-8") as f:
            lines = f.readlines()
        events = []
        for line in lines[-limit:]:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return {"agent": agent, "events": events}
    except OSError:
        return {"agent": agent, "events": []}


# ── entrypoint ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
