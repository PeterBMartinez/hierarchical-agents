import json
import os
from datetime import datetime

STATE_DIR = os.environ.get("AGENT_STATE_DIR", os.path.join("dashboard", "state"))

ROLE_LABELS = {
    "orchestrator": "Orchestrator",
    "researcher": "Research Analyst",
    "business_ops": "Operations",
    "claude_code": "Code Engineer",
}

EVENT_FIELDS = ("name", "role", "status", "task", "model", "kind")


def role_for(name: str) -> str:
    return ROLE_LABELS.get(name, name.replace("_", " ").title())


def kind_for(name: str, kind) -> str:
    if kind:
        return kind
    return "orchestrator" if name == "orchestrator" else "worker"


def _safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name) or "agent"


def report(name, status, task="", model="", kind=None, role=None) -> None:
    if not STATE_DIR:
        return
    record = {
        "name": name,
        "role": role or role_for(name),
        "status": status,
        "task": task,
        "model": model,
        "kind": kind_for(name, kind),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    _write_agent(record)
    _append_event(record)


def _write_agent(record) -> None:
    try:
        directory = os.path.join(STATE_DIR, "agents")
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"{_safe_name(record['name'])}.json")
        temp = f"{path}.tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(record, handle)
        os.replace(temp, path)
    except OSError:
        pass


def _append_event(record) -> None:
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        event = {"ts": record["updated_at"]}
        event.update({field: record[field] for field in EVENT_FIELDS})
        with open(os.path.join(STATE_DIR, "events.jsonl"), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")
    except OSError:
        pass


def run_reported(worker, task: str, model: str = "") -> str:
    report(worker.name, "working", task, model)
    try:
        result = worker.run(task)
    except Exception:
        report(worker.name, "error", task, model)
        raise
    report(worker.name, "done", task, model)
    return result
