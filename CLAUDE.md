# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Two distinct systems in one repo

This repo contains two separate stacks that share some helpers but run independently:

| System | Entry point | Python env | Where it runs |
|---|---|---|---|
| **Agent swarm** (`agents_app/`) | `python -m agents_app.runner "<goal>"` | `.venv` (Anthropic SDK) | Mac or Docker |
| **Mission deck** (`dashboard/`) | `uvicorn server:app` (via systemd) | `venv` (FastAPI) | pi-02 only |

Never mix the two venvs. The dashboard `venv` lives at `/home/peter/hierarchical-agents/venv` on pi-02. The SDK venv is `.venv` in the repo root.

## Commands

### Agent swarm (local / Docker)

```bash
# Setup (first time)
python -m venv .venv && source .venv/bin/activate
pip install -U -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY

# Run a goal
set -a; source .env; set +a
python -m agents_app.runner "Research X, then draft a plan for Y"

# Docker equivalent
docker compose run --rm agents "Research X, then draft a plan for Y"
```

### Dashboard (pi-02)

```bash
# Deploy changed files
scp dashboard/server.py dashboard/mission-control.dc.html peter@100.99.6.88:/home/peter/hierarchical-agents/dashboard/

# Restart the server
ssh peter@100.99.6.88 "sudo systemctl restart agent-dashboard"

# Restart a watcher
ssh peter@100.99.6.88 "sudo systemctl restart helm-watcher"
ssh peter@100.99.6.88 "sudo systemctl restart ops-watcher"

# Live logs
ssh peter@100.99.6.88 "journalctl -u agent-dashboard -f"
ssh peter@100.99.6.88 "journalctl -u helm-watcher -f"

# Watch the raw event stream
ssh peter@100.99.6.88 "tail -f /home/peter/hierarchical-agents/dashboard/state/events.jsonl"

# Trigger banner scan immediately
ssh peter@100.99.6.88 "bash /home/peter/hierarchical-agents/banner/important-scan.sh"
```

### Local dashboard dev (not on pi)

```bash
cd dashboard
AGENT_STATE_DIR=state DAILY_BUDGET_USD=5 python3 server.py
# open http://localhost:8787
```

## Environment variables

| Variable | Used by | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | agents_app swarm | required |
| `ORCHESTRATOR_MODEL` | `config.py` | `claude-opus-4-8` |
| `WORKER_MODEL` | `config.py` | `claude-opus-4-8` |
| `ENABLE_CLAUDE_CODE_WORKER` | `runner.py` | off |
| `AGENT_STATE_DIR` | dashboard server + watcher scripts | `dashboard/state` |
| `DASHBOARD_PORT` | `server.py` | `8787` |
| `DAILY_BUDGET_USD` | cost monitor | `5` |
| `COST_LOG_PATH` | cost monitor | `~/.claude/cost-log.jsonl` |

## Architecture: agent swarm (`agents_app/`)

The orchestrator runs a **`tool_runner` loop** (Anthropic Beta SDK) where each delegation tool is a decorated Python function. When the orchestrator calls `delegate_to_researcher(task)`, that function runs the worker synchronously and returns its string output back into the tool result. Workers are isolated — they get a fresh context and cannot see each other or the main conversation.

Delegation is sequential today. The README notes `asyncio.gather()` as the next scaling step.

**To add a worker:**
1. Create `agents_app/workers/<name>.py` implementing `Worker` (`name`, `run(task) -> str`)
2. Register it in `runner.py`'s `build_orchestrator`
3. Add a `@beta_tool def delegate_to_<name>` in `orchestrator.py`

## Architecture: mission deck (`dashboard/`)

### State store

All state is JSONL flat files on pi-02 under `dashboard/state/`. `activity.py` is the only writer for agent records and events; everything else reads. Agent JSON files are written atomically (temp + `os.replace`).

The critical dual-write pattern: every conversation append writes to **both** `state/threads/<agent>/<conv_id>.jsonl` (the real store) and `state/threads/<agent>.jsonl` (the legacy flat file). The legacy file exists solely as the `inotifywait` target — watching a file is simpler than watching a directory.

### Watcher trigger loop

`helm-watcher.sh` and `ops-watcher.sh` follow this pattern:
1. `inotifywait` blocks on the legacy flat file
2. On any write event, `sleep 0.4` (debounce), then call `process()`
3. `process()` acquires `flock -n 9` (skips if Claude is already running), checks `hermit_chat.py inbox`, then fires `claude -p "$PROMPT"` with the last 10 messages as context
4. Falls back to `stat` polling if `inotifywait` is unavailable

### Delegation forwarding

When helm delegates to a worker via `hermit_chat.py send --to ops --text "task" --from helm`, the message is written to ops's thread with `"delegator": "helm"`. When ops later calls `hermit_chat.py reply`, the reply code detects the `delegator` field and auto-appends a forwarded copy (`↩ from ops: ...`) to helm's thread. No extra plumbing needed.

### WebSocket push

`server.py` runs `_state_broadcaster()` as an asyncio background task. Every 2 seconds it calls `build_state()`, computes a signature over `(name, status, task, updated_at)` for all agents, and broadcasts to all WebSocket clients if the signature changed. The dashboard also keeps a 30-second fallback REST poll and a 3-second thread-refresh poll.

### Dashboard frontend

`mission-control.dc.html` is a single-file DC-format component (no build step). `support.js` is the runtime that boots React 18 from unpkg CDN and renders the `<x-dc>` template. The component class in `<script type="text/x-dc">` follows React class component conventions: `state`, `componentDidMount`, `componentDidUpdate`, `componentWillUnmount`, and `renderVals()` (returns the view-model object the template binds to via `{{ }}`).

## Scheduled jobs on pi-02

| Schedule | Script | Output |
|---|---|---|
| Every 15 min | `cost-monitor/cost_monitor.py` | Reads `~/.claude/cost-log.jsonl`, logs spend |
| Every hour | `banner/important-scan.sh` | Writes `state/important.json` (dashboard banner) |
| 7am + noon MT (weekdays) | `briefing/run-briefing.sh` | Full project digest → `briefing/last-briefing.txt` |

## MCP tools available to agents on pi-02

All `claude -p` invocations on pi-02 have access to: **Notion**, **ClickUp**, **Microsoft 365** (Teams, Outlook, SharePoint), **Azure DevOps** (custom connector), **cluster-rag** (pi-01 RAG API), and **web search/fetch**.

## Key files

| File | Purpose |
|---|---|
| `agents_app/orchestrator.py` | Tool-runner loop + delegation tool definitions |
| `agents_app/activity.py` | Core state writer — the only path to `state/agents/` and `events.jsonl` |
| `dashboard/server.py` | FastAPI app, WebSocket broadcaster, all REST routes, conversation helpers |
| `dashboard/mission-control.dc.html` | Dashboard UI — template + component class |
| `dashboard/hermit_chat.py` | CLI used inside agent runs: `inbox` / `reply` / `send` / `thread` |
| `dashboard/report.py` | CLI wrapper around `activity.report()` — called by watcher scripts |
| `dashboard/helm-watcher.sh` | inotifywait → Claude Code bridge for helm |
| `dashboard/ops-watcher.sh` | inotifywait → Claude Code bridge for ops |
| `ARCHITECTURE.md` | Detailed component reference with data format examples |
