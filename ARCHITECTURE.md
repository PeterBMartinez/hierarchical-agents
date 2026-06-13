# Agent Operations Center — Architecture

## Overview

A self-hosted AI agent operations system running on a Raspberry Pi cluster. The user interacts through a web dashboard to chat with agents, monitor their status, and review delivery work items. Agents run continuously as background processes, responding autonomously to messages via event-driven watchers.

---

## Network Topology

```
MacBook (100.126.245.12)
  └─ browser → pi-02:8787

pi-01 (100.84.93.86)
  └─ cluster-rag API :8080  (RAG search over internal docs)

pi-02 (100.99.6.88)  ← main compute node
  ├─ agent-dashboard.service  (:8787)
  ├─ helm-watcher.service
  ├─ atlas-watcher.service
  ├─ ops-watcher.service
  ├─ net-watcher.service
  ├─ brand-watcher.service
  └─ cron: briefing, banner, cost-monitor

pi-03 (100.121.226.64)
  └─ n8n :5678  (workflow automation)
  └─ jobhunter app :4317/:5317
```

All nodes connected via Tailscale VPN. No public exposure.

---

## Components

### 1. Dashboard Server (`dashboard/server.py`)

FastAPI + Uvicorn ASGI app on pi-02 port 8787. Serves the dashboard UI and a JSON/WebSocket API.

**API endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/agents` | All agent records |
| GET | `/api/agent?agent=X&conv_id=Y` | Single agent + conversation thread |
| GET | `/api/conversations?agent=X` | List conversations for an agent |
| GET | `/api/analytics` | Token cost breakdown by period and agent |
| GET | `/api/log?agent=X` | Recent stream-json log events for an agent |
| POST | `/api/conversations` | Create a new conversation |
| POST | `/api/activate` | Switch the active conversation |
| POST | `/api/message` | Append a user message |
| POST | `/api/model` | Change the Claude model for an agent |
| DELETE | `/api/conversations` | Delete a conversation |
| WS | `/ws` | WebSocket push — broadcasts state changes every 2s |

**State directory:** `dashboard/state/`

```
state/
  agents/
    helm.json          ← live status record {name, role, status, task, model, kind, updated_at}
    atlas.json
    ops.json
    net.json
    brand.json
  threads/
    helm/
      index.json       ← [{id, title, created_at, updated_at, active}]
      3fbfc9e8.jsonl   ← one JSONL per conversation, one message per line
    atlas/  ops/  net/  brand/  (same structure)
    helm.jsonl         ← legacy flat file — kept in sync for inotifywait trigger
    atlas.jsonl  ops.jsonl  net.jsonl  brand.jsonl
  logs/
    helm.jsonl         ← stream-json events: {ts, kind, text}
    atlas.jsonl  ops.jsonl  net.jsonl  brand.jsonl
  events.jsonl         ← append-only agent event log
  important.json       ← banner data from Notion To-Do board
  models.json          ← per-agent model overrides {helm: "sonnet", ...}
```

**Dual-write pattern:** Every `append_message()` call writes to both the active conversation file (`threads/<agent>/<conv_id>.jsonl`) and the legacy flat file (`threads/<agent>.jsonl`). The legacy file is the inotifywait target — writing to it fires the watcher.

**WebSocket push:** `_state_broadcaster()` runs as an asyncio background task, computing a signature over all agent state every 2 seconds and broadcasting to all connected clients if anything changed.

---

### 2. Agent Roster

Five always-on agents, each a separate systemd service on pi-02:

| Agent | Kind | Default Model | Trigger | Role |
|-------|------|---------------|---------|------|
| **helm** | orchestrator | sonnet | inotifywait on `threads/helm.jsonl` | Routes user requests; delegates to specialists; surfaces routing suggestions with alternatives |
| **atlas** | hermit | sonnet | inotifywait on `threads/atlas.jsonl` | Research, deep-dives, automation topics; saves findings to Notion |
| **ops** | hermit | haiku | inotifywait on `threads/ops.jsonl` | Delivery + comms: Aria, TruckSpy, Warp 9, Teams, Outlook, ClickUp |
| **net** | hermit | sonnet | inotifywait on `threads/net.jsonl` | Personal network: contact logging, follow-ups, re-engagement drafts |
| **brand** | hermit | sonnet | inotifywait on `threads/brand.jsonl` | Personal brand: LinkedIn/X content drafts, campaign plans, engagement analysis via MCP |

**Message flow (user → agent → reply):**

```
User types in dashboard
  → POST /api/message  (writes to conv file + legacy flat)
  → inotifywait fires on legacy flat file
  → process() in watcher script
      → flock -n 9  (skips if Claude already running)
      → hermit_chat.py inbox  → finds unanswered messages
      → builds FULL_PROMPT: system prompt + live agent roster + date/time + last 10 messages
      → claude -p "$FULL_PROMPT" --output-format stream-json --verbose
          → parse_stream.py  → writes {ts, kind, text} events to state/logs/<agent>.jsonl
          → agent calls hermit_chat.py reply  → appends to conv + legacy flat
  → WebSocket broadcast (within 2s) → dashboard re-renders thread
```

**Delegation flow (helm → specialist):**

```
helm receives message
  → hermit_chat.py send --to atlas --text "..." --from helm
      → creates new conv in atlas's thread
      → appends message with {delegator: "helm"}
      → writes to atlas.jsonl  → fires atlas watcher
  → atlas does work, calls hermit_chat.py reply --name atlas --text "..."
      → appends to atlas conv
      → detects delegator=helm  → also appends "↩ from atlas: ..." to helm's conv
  → helm's COMMS tab shows the forwarded reply automatically
```

---

### 3. Watcher Services

Each watcher script (`dashboard/<agent>-watcher.sh`) follows the same pattern:

1. `inotifywait -t 30` blocks on the agent's legacy flat file (30s timeout catches missed events)
2. On write event: `sleep 0.4` debounce → call `process()`
3. `process()`: acquire `flock -n 9` → check inbox → build prompt with live context → `claude -p` → report status
4. Falls back to `stat` polling if inotifywait unavailable

Each watcher is a systemd service (`Restart=always`) that auto-restarts on crash.

**Prompt construction per agent:**
- System prompt (role, tools, step-by-step instructions)
- `AVAILABLE AGENTS` block (helm only — live roster read from `state/agents/`)
- `TODAY` / `NOW` date-time injection (so agents compute absolute dates correctly)
- `RECENT CONVERSATION HISTORY` (last 10 messages from the active conv)

**Output pipeline:**
```
claude -p ... --output-format stream-json --verbose 2>/dev/null \
  | python3 parse_stream.py --name <agent>
```
`parse_stream.py` reads NDJSON from Claude's stream, extracts text/tool/thinking events, and appends to `state/logs/<agent>.jsonl`.

---

### 4. CLI Bridge (`dashboard/hermit_chat.py`)

Python script used by agents inside their `claude -p` sessions:

```bash
hermit_chat.py inbox --name helm             # print unanswered messages in active conv
hermit_chat.py reply --name helm --text "…"  # append agent reply + trigger delegation forward
hermit_chat.py send --to atlas --text "…" --from helm  # delegate; sets delegator field
hermit_chat.py thread --name atlas           # dump full active conversation
```

Imports `server.py` functions directly — no HTTP overhead. Always run with `AGENT_STATE_DIR` set.

---

### 5. Briefing System (`briefing/`)

Runs at 7am and noon MT (weekdays) via cron.

`run-briefing.sh` → `claude -p "$(cat briefing-prompt.txt)"`:
1. Reads Aria PRs (Azure DevOps), TruckSpy/Warp 9 work items (ClickUp), Teams/Outlook comms
2. Reconciles the Notion "Delivery To-Do" board
3. Sends a digest to ops's inbox via `hermit_chat.py send --to ops`

---

### 6. Banner / Important Scan (`banner/`)

Runs hourly via cron.

`important-scan.sh` → `claude -p`: reads the Notion "Delivery To-Do" board, filters to active items, writes `state/important.json`. Dashboard renders this as the top banner with a "View in Notion" button per item.

---

### 7. Cost Monitor (`cost-monitor/`)

Runs every 15 minutes via cron. Reads `~/.claude/cost-log.jsonl`, computes daily/weekly spend per agent, included in `/api/agents` responses.

---

### 8. MCP Tools (Claude Extensions)

Configured in `~/.claude.json` on pi-02. Available to all `claude -p` invocations:

| Tool set | Purpose |
|----------|---------|
| **Notion** | Read/write pages and databases (To-Do board, Content Queue, Research Digest) |
| **ClickUp** | Read/write TruckSpy and Warp 9 work items |
| **Microsoft 365** | Teams messages, Outlook email, SharePoint |
| **Azure DevOps** | Aria PRs and work items (custom connector) |
| **cluster-rag** | RAG search over internal cluster documentation (pi-01 :8080) |
| **Web search / fetch** | General research |
| **LinkedIn MCP** | LinkedIn analytics for brand agent (Supergrow or equivalent) |

---

### 9. Dashboard Frontend (`dashboard/mission-control.dc.html`)

Single-file DC-format component — no build step. `support.js` boots React 18 from CDN and renders the `<x-dc>` template.

The component class (`class Component extends DCLogic`) follows React class component conventions: `state`, `componentDidMount`, `componentDidUpdate`, `componentWillUnmount`, `renderVals()` (returns the view-model object templates bind to via `{{ }}`).

**Layout (desktop):**
```
┌─────────────────────────────────────────────────────────┐
│  BANNER  (Notion To-Do items + View in Notion button)   │
├─────────────────────────────────────────────────────────┤
│  HEADER  (brand · active count · cost · clock)          │
├──────────────┬──────────────────────────┬───────────────┤
│  ROSTER      │  FACILITY MAP            │  INSPECTOR    │
│  (5 agents)  │  (animated bot SVGs)     │  OVERVIEW     │
│              │  + TICKER event stream   │  ACTIVITY     │
│              │                          │  TUNE         │
│              │                          │  COMMS        │
└──────────────┴──────────────────────────┴───────────────┘
```

**Mobile:** header collapses non-essential elements (`m-hide`), COMMS uses master-detail (full-width list OR full-width thread, never both). iOS input zoom prevented by `font-size: 16px` override.

**Polling:** WebSocket for push + 30s fallback REST poll + 3s thread refresh when COMMS is open. `_pollAgents()` called immediately on mount (no cold-start delay).

**Performance:** `shouldComponentUpdate` guards all renders; bot SVGs memoized via `_botCache` keyed on `${name}:${status}:${size}` to prevent animation restarts on re-render.

---

## Data Formats

**Agent record** (`state/agents/<name>.json`):
```json
{
  "name": "helm",
  "role": "Orchestrator",
  "status": "idle",
  "task": "Awaiting orders",
  "model": "sonnet",
  "kind": "orchestrator",
  "desc": "Routes requests and delegates to specialists.",
  "updated_at": "2026-06-13T14:00:00"
}
```

**Conversation message** (one line in `.jsonl`):
```json
{"ts": "2026-06-13T14:20:08", "from": "user", "text": "Draft a LinkedIn post about X.", "delegator": "helm"}
{"ts": "2026-06-13T14:21:35", "from": "agent", "text": "Done. Saved to Notion: ..."}
```

**Stream log event** (`state/logs/<agent>.jsonl`):
```json
{"ts": "2026-06-13T14:20:10", "kind": "thinking", "text": "Reading inbox first."}
{"ts": "2026-06-13T14:20:11", "kind": "tool", "text": "Bash: hermit_chat.py inbox --name brand"}
{"ts": "2026-06-13T14:21:34", "kind": "text", "text": "Done. Both variants saved to Notion."}
```

**Banner item** (`state/important.json`):
```json
{
  "updated": "2026-06-13T13:00:00Z",
  "items": [
    {"kind": "todo", "task": "Review Aria PR #142", "project": "Aria", "priority": "High", "status": "In Progress", "url": "https://..."}
  ]
}
```

---

## Deployment

- **Host:** pi-02, Tailscale `100.99.6.88`, user `peter` (UID 1000)
- **Working directory:** `/home/peter/hierarchical-agents/`
- **Python venv:** `/home/peter/hierarchical-agents/venv` (FastAPI, uvicorn)
- **Services:** `agent-dashboard`, `helm-watcher`, `atlas-watcher`, `ops-watcher`, `net-watcher`, `brand-watcher` (systemd, `Restart=always`)
- **Claude Code:** installed system-wide; agents invoke as `claude -p`
- **Cron jobs:** briefing (7am + noon MT), banner (hourly), cost-monitor (every 15 min)
- **No containers** for dashboard stack — bare Python 3 on Pi OS
