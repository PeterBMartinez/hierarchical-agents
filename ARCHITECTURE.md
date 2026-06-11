# Agent Operations Center — Architecture

## Overview

A self-hosted AI agent operations system running on a Raspberry Pi (pi-02). The user interacts through a web dashboard to chat with agents, monitor their status, and review delivery work items. Agents run continuously as background processes and respond autonomously to messages and scheduled triggers.

---

## Network Topology

```
MacBook (100.126.245.12)          pi-01 (100.84.93.86)
  └─ browser → :8787        ←──  └─ cluster-rag API :8080
                                        │  (RAG search over cluster docs)
                            pi-02 (100.99.6.88)  ←── all services run here
                              ├─ agent-dashboard.service  (:8787)
                              ├─ helm-watcher.service
                              ├─ atlas-watcher.service
                              └─ cron jobs (ops, briefing, banner)
```

All nodes are connected via Tailscale VPN. Access is private — no public exposure.

---

## Components

### 1. Dashboard Server (`dashboard/server.py`)

A single-file Python `ThreadingHTTPServer`. Serves `index.html` and a JSON API. No framework dependencies.

**API endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/agents` | Full state snapshot: all agent records, recent events, cost, banner items |
| GET | `/api/agent?agent=X&conv_id=Y` | Single agent detail: status, events, conversation thread |
| GET | `/api/conversations?agent=X` | List all conversations for an agent |
| POST | `/api/conversations` | Create a new conversation |
| POST | `/api/activate` | Switch the active conversation |
| DELETE | `/api/conversations` | Delete a conversation and its file |
| POST | `/api/message` | Append a user message to a conversation |
| POST | `/api/model` | Change the Claude model for an agent |
| GET | `/api/analytics` | Token cost breakdown by period and agent |

**State directory:** `dashboard/state/`

```
state/
  agents/
    helm.json          ← live status record (name, role, status, task, model, updated_at)
    atlas.json
    ops.json
  threads/
    helm/
      index.json       ← conversation list [{id, title, created_at, updated_at, active}]
      3fbfc9e8.jsonl   ← one JSONL per conversation, one message per line
      cbba7e5e.jsonl
    atlas/
      ...
    ops/
      ...
    helm.jsonl         ← legacy flat file kept in sync for watcher triggers
    atlas.jsonl
    ops.jsonl
  events.jsonl         ← append-only event log (name, status, task, ts)
  important.json       ← banner data from Notion To-Do board scan
  models.json          ← per-agent model overrides {helm: "sonnet", ...}
```

**Conversation model:**
- Each agent has a directory of JSONL files, one per conversation
- `index.json` tracks metadata and which conversation is active
- On first access, existing flat `<agent>.jsonl` files are automatically migrated into the first conversation
- The legacy flat files continue to be written to so `inotifywait` watchers still fire

---

### 2. Agents

Three always-on agents, each with a distinct role:

| Agent | Kind | Model | Trigger | Role |
|-------|------|-------|---------|------|
| **helm** | orchestrator | sonnet | inotifywait on `threads/helm.jsonl` | Routes user requests; delegates to atlas or ops; replies via `hermit_chat.py reply` |
| **atlas** | hermit | sonnet | inotifywait on `threads/atlas.jsonl` | Research tasks; saves findings to Notion "AI Research Digest"; replies with Notion link |
| **ops** | ops | haiku | cron every 3 min | Delivery coordinator; reads Notion To-Do board; answers questions about Aria, TruckSpy, Warp 9 |

**Message flow (user → agent → reply):**

```
User types in dashboard
  → POST /api/message (writes to conv file + legacy flat)
  → inotifywait fires on legacy flat file
  → process() in watcher script
      → hermit_chat.py inbox → reads active conv → finds unanswered messages
      → reads THREAD_CTX from active conv (last 10 messages)
      → claude -p "<system prompt>\n<thread context>" --max-turns 30
          → agent reads inbox, does work, calls hermit_chat.py reply
          → reply appends to active conv + legacy flat
  → dashboard tick (every 2s) → GET /api/agent → re-renders thread
```

**Delegation flow (helm → atlas/ops):**

```
helm receives message
  → decides to delegate
  → hermit_chat.py send --to atlas --text "..." --from helm
      → appends to atlas's active conv with {delegator: "helm"}
      → fires atlas watcher
  → atlas does work
  → hermit_chat.py reply --name atlas --text "..."
      → appends to atlas conv
      → finds delegator=helm → also appends "↩ from atlas: ..." to helm's active conv
  → helm's thread shows the forwarded reply
```

---

### 3. Watcher Services

**helm-watcher.service / atlas-watcher.service** (systemd):
- Run `helm-watcher.sh` / `atlas-watcher.sh` as persistent daemon
- Use `inotifywait` to watch for writes to the legacy flat file
- `flock` prevents concurrent runs
- On trigger: check inbox → build prompt + thread context → `claude -p` → report status

**ops-responder.sh** (cron, every 3 minutes):
- Same pattern but cron-driven instead of event-driven
- Checks inbox; exits immediately if nothing pending

---

### 4. Briefing System (`briefing/`)

Runs twice daily (7am and 12pm Mountain) via cron.

**run-briefing.sh** → `claude -p "$(cat briefing-prompt.txt)"`:
1. Reads Aria PRs (Azure DevOps), TruckSpy and Warp 9 work items (ClickUp), Teams/Outlook comms
2. Reconciles the Notion "Delivery To-Do" board — marks completed items Done, adds new ones
3. Sends a summary to ops's inbox via `hermit_chat.py send --to ops`

---

### 5. Banner / Important Scan (`banner/`)

Runs hourly via cron.

**important-scan.sh** → `claude -p "$(cat important-prompt.txt)"`:
1. Reads the Notion "Delivery To-Do" board (collection `0fff06e2-62de-4d1f-80e4-b75e25e50fc6`)
2. Filters to Todo and In Progress only (discards Done)
3. Writes `state/important.json` — up to 10 items sorted by priority

Dashboard reads this file on every tick and renders it as the top banner.

---

### 6. CLI Bridge (`dashboard/hermit_chat.py`)

Python script used by agents inside their `claude -p` sessions to communicate with the message bus:

```bash
hermit_chat.py inbox --name helm             # print unanswered messages in active conv
hermit_chat.py reply --name helm --text "…"  # append agent reply to active conv
hermit_chat.py send --to atlas --text "…" --from helm   # delegate; sets delegator field
hermit_chat.py thread --name atlas           # dump full conversation history
```

All operations route through `server.py` functions (imported directly) for conversation-aware I/O.

---

### 7. Cost Monitor (`cost-monitor/`)

Runs every 15 minutes via cron. Reads Claude's cost log (`~/.claude/cost-log.jsonl`), computes daily spend, and writes a status record. The dashboard server loads this at request time and includes it in `/api/agents` responses.

---

### 8. MCP Tools (Claude Extensions)

Configured in `~/.claude.json` on pi-02. Available to all `claude -p` invocations:

| Tool set | Purpose |
|----------|---------|
| **Notion** | Read/write Notion pages and databases (To-Do board, AI Research Digest) |
| **ClickUp** | Read work items from TruckSpy and Warp 9 spaces |
| **Microsoft 365** | Read Teams messages, Outlook email, SharePoint |
| **Azure DevOps** (via custom connector) | Read Aria PRs and work items |
| **cluster-rag** | RAG search over internal cluster documentation (served by pi-01) |
| **Web search / fetch** | General research |

---

### 9. Dashboard Frontend (`dashboard/index.html`)

Single-file, zero-build frontend. All CSS and JS inline.

**Layout:**
```
┌─────────────────────────────────────────────────────────┐
│  BANNER (Notion To-Do items, hidden if empty)           │
├─────────────────────────────────────────────────────────┤
│  HEADER (brand, metrics: active count, cost, clock)     │
├──────────────┬──────────────────────────┬───────────────┤
│  ROSTER      │  FACILITY MAP            │  INSPECTOR    │
│  (agent list)│  (bot visualizations)    │  (opens when  │
│              │  + TICKER (event stream) │   agent       │
│              │                          │   clicked)    │
└──────────────┴──────────────────────────┴───────────────┘
```

Inspector opens as a third grid column (desktop) or full-screen overlay (mobile). Contains four tabs:

- **OVERVIEW** — agent status, role, model, task counts
- **ACTIVITY** — event log for this agent
- **TUNE** — model switcher (haiku/sonnet/opus) + quick directive buttons
- **COMMS** — multi-conversation chat interface

**COMMS tab layout:**
```
┌──────────────┬─────────────────────────────────┐
│ conv sidebar │  message thread                 │
│ + NEW CHAT   │  [agent reply with markdown]    │
│ ─────────    │  [user message]                 │
│ Chat title   │  [agent reply]                  │
│ 3h ago      │                                 │
│ ─────────    │  ──────────────────────────     │
│ Chat 2       │  [input box]  [HAIL button]     │
│ yesterday    │                                 │
└──────────────┴─────────────────────────────────┘
```

**Polling:** `setInterval(tick, 2000)` — fetches `/api/agents` every 2 seconds. When inspector is open, also fetches `/api/agent` with the active conversation ID.

---

## Data Formats

**Agent record** (`state/agents/<name>.json`):
```json
{"name":"helm","role":"Orchestrator","status":"idle","task":"Awaiting orders","model":"","kind":"orchestrator","updated_at":"2026-06-11T14:59:22"}
```

**Conversation message** (one line in `.jsonl`):
```json
{"ts":"2026-06-11T14:49:08","from":"user","text":"What's the status of the TruckSpy sprint?"}
{"ts":"2026-06-11T14:49:31","from":"agent","text":"I'll check with ops and report back.","via":"ops"}
```

**Important banner** (`state/important.json`):
```json
{"updated":"2026-06-11T13:00:00Z","items":[
  {"kind":"todo","task":"Review Aria PR #142","project":"Aria","priority":"High","status":"In Progress"},
  {"kind":"todo","task":"Reply to TruckSpy standup thread","project":"TruckSpy","priority":"Medium","status":"Todo"}
]}
```

---

## Deployment

- **Host:** Raspberry Pi 5, `pi-02`, Tailscale IP `100.99.6.88`
- **Working directory:** `/home/peter/hierarchical-agents/`
- **Services:** `agent-dashboard.service`, `helm-watcher.service`, `atlas-watcher.service` (systemd)
- **Cron jobs:** ops-responder every 3 min, briefing at 7am/12pm MT, important-scan hourly, cost-monitor every 15 min
- **Claude Code** installed system-wide; agents invoke it as `claude -p`
- **No containers** for the dashboard stack — bare Python 3 on the Pi OS
