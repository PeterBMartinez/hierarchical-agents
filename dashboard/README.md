# Mission Deck (Dashboard)

A dependency-free live dashboard for the agent swarm. A Python stdlib server serves
one HTML page that polls `/api/agents` every 2s and renders:

- **Crew roster** (left) — every agent: name, type tag, role, status, current task.
- **Facility map** (right) — a hub-and-spoke layout with the **master orchestrator
  in the central room** and all other agents arranged around it, connected by links
  that light up when an agent is working.
- **Event ticker** (bottom) — a scrolling live feed of recent delegations/results.
- **Spend gauge** (header) — today's cost vs budget, wired to the cost monitor.

Status drives color everywhere: idle (dim cyan), planning (violet), working (amber,
pulsing), done (green), error (red).

## Run

Run from the project root (`hierarchical-agents/`) so relative state paths line up:

```bash
AGENT_STATE_DIR=dashboard/state DAILY_BUDGET_USD=5 python3 dashboard/server.py
# open http://localhost:8787  (or http://<pi-tailscale-ip>:8787 from any device)
```

In Docker it runs as the `dashboard` service — see the project README.

## How agents appear: the status store

Any process that writes `dashboard/state/agents/<name>.json` shows up on the deck.
The Python app does this automatically (see `agents_app/activity.py`). The schema:

```json
{
  "name": "researcher",
  "role": "Research Analyst",
  "status": "working",          // idle | planning | working | done | error
  "task": "Survey agentic patterns across 5 sources",
  "model": "claude-sonnet-4-6",
  "kind": "worker",             // orchestrator | worker | hermit | watch | ...
  "updated_at": "2026-06-08T21:30:00"
}
```

- Exactly one agent with `kind: "orchestrator"` (or name `orchestrator`) is placed in
  the central room. Everything else orbits it.
- `kind` is free-form — add your own types; unknown kinds get a default glyph.
- Each status write also appends to `dashboard/state/events.jsonl`, which feeds the ticker.

## Wire in hermit (or anything else)

Hermits surface themselves by calling the bundled adapter from a routine/watch:

```bash
python3 /path/to/hierarchical-agents/dashboard/report.py \
  --name dev-hermit --role "Dev Hermit" --kind hermit \
  --status working --task "Watching open PRs and gating merges"
```

Call it with `--status working` when a routine starts and `--status done` (or `idle`)
when it finishes. The hermit then appears as its own room on the map and in the feed,
alongside the Python swarm — multiple agent types on one board.

## Endpoints

- `GET /` — the dashboard page.
- `GET /api/agents` — `{ agents, events, cost, now }` JSON.
