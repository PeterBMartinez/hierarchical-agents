#!/usr/bin/env python3
import argparse
import json
import os
import sys
from datetime import datetime

ap = argparse.ArgumentParser()
ap.add_argument("--name", required=True)
args = ap.parse_args()

STATE_DIR = os.environ.get(
    "AGENT_STATE_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "state"),
)
LOGS_DIR = os.path.join(STATE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOGS_DIR, f"{args.name}.jsonl")

open(LOG_PATH, "w").close()


def now():
    return datetime.now().isoformat(timespec="seconds")


def write_event(kind, text):
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps({"ts": now(), "kind": kind, "text": text}) + "\n")


def input_summary(inp):
    if not isinstance(inp, dict) or not inp:
        return ""
    for key in ("query", "text", "command", "path", "url", "description", "task", "prompt"):
        if key in inp:
            return str(inp[key]).strip().replace("\n", " ")[:140]
    first = str(next(iter(inp.values()), "")).strip().replace("\n", " ")
    return first[:140]


for raw in sys.stdin:
    raw = raw.strip()
    if not raw:
        continue
    try:
        ev = json.loads(raw)
    except json.JSONDecodeError:
        continue

    kind = ev.get("type")
    if kind == "assistant":
        for block in (ev.get("message") or {}).get("content", []):
            btype = block.get("type")
            if btype == "text":
                text = (block.get("text") or "").strip()
                if text:
                    write_event("thinking", text[:300])
            elif btype == "tool_use":
                tool = block.get("name", "?")
                summary = input_summary(block.get("input", {}))
                write_event("tool", tool + (f": {summary}" if summary else ""))
    elif kind == "result":
        sub = ev.get("subtype", "")
        write_event("result", "Completed" if sub == "success" else f"Ended: {sub}")
