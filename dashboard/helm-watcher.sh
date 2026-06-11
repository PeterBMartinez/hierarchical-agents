#!/usr/bin/env bash
export HOME=/home/peter
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export AGENT_STATE_DIR=/home/peter/hierarchical-agents/dashboard/state
DASH=/home/peter/hierarchical-agents/dashboard
THREAD="$AGENT_STATE_DIR/threads/helm.jsonl"
mkdir -p "$(dirname "$THREAD")"
touch "$THREAD"

agent_model(){ /usr/bin/python3 -c "import json,os;p=os.path.join('$AGENT_STATE_DIR','models.json');d=json.load(open(p)) if os.path.isfile(p) else {};print(d.get('$1') or 'sonnet')" 2>/dev/null || echo sonnet; }

read -r -d '' PROMPT <<'EOF'
You are helm, the orchestrator on the mission-control dashboard. The user just sent you a message. Handle it now, then stop.

STEP 1 — Read your inbox:
   /usr/bin/python3 /home/peter/hierarchical-agents/dashboard/hermit_chat.py inbox --name helm

STEP 2 — Decide: answer directly, or delegate to a specialist.
   - Answer directly for status, summaries, coordination, quick questions — use READ-ONLY connector data when useful.
   - DELEGATE real work: atlas = research / automation topics; ops = delivery + comms / project status (Aria, TruckSpy, Warp 9, Teams, Outlook).

STEP 3 — If you delegate, you MUST actually RUN this exact command via Bash (never just claim you routed it):
   /usr/bin/python3 /home/peter/hierarchical-agents/dashboard/hermit_chat.py send --to <atlas|ops> --text "THE FULL TASK" --from helm
   The --from helm flag is REQUIRED: it is the ONLY thing that makes the worker's report come back into this thread automatically. Never omit --from helm. A claim that you delegated is only true if this command actually ran and returned "task sent to <agent>".

STEP 4 — ALWAYS finish by posting one reply to the user:
   /usr/bin/python3 /home/peter/hierarchical-agents/dashboard/hermit_chat.py reply --name helm --text "YOUR REPLY"
   If you delegated, your reply should say you handed it to <atlas|ops> and that their report will appear here automatically when ready.

Rules: read-only; do NOT send emails/Teams or modify ClickUp/Azure DevOps. Delegate ONLY via the STEP 3 send command; reply ONLY via the STEP 4 reply command. Be concise.
EOF

process() {
  exec 9>/tmp/helm-watcher.lock
  flock -n 9 || return 0
  PENDING=$(/usr/bin/python3 "$DASH/hermit_chat.py" inbox --name helm 2>/dev/null)
  [ -z "$PENDING" ] && return 0
  [ "$PENDING" = "(no new messages)" ] && return 0
  MODEL=$(agent_model helm); [ -z "$MODEL" ] && MODEL=sonnet

  THREAD_CTX=$(/usr/bin/python3 - <<'PYEOF'
import json, os
base = '/home/peter/hierarchical-agents/dashboard/state/threads'
try:
    idx = os.path.join(base, 'helm', 'index.json')
    conv_id = None
    if os.path.isfile(idx):
        for c in json.load(open(idx)):
            if c.get('active'):
                conv_id = c['id']; break
    path = os.path.join(base, 'helm', conv_id+'.jsonl') if conv_id else os.path.join(base, 'helm.jsonl')
    lines = open(path).readlines() if os.path.isfile(path) else []
    recent = []
    for line in lines[-10:]:
        try:
            m = json.loads(line.strip())
            who = m.get('from') or '?'
            text = (m.get('text') or '').strip().replace('\n', ' ')[:300]
            ts = (m.get('ts') or '')[:16]
            recent.append(f'[{ts}] {who}: {text}')
        except: pass
    print('\n'.join(recent))
except: pass
PYEOF
)

  FULL_PROMPT="${PROMPT}

RECENT CONVERSATION HISTORY (last 10 messages — use this for context on what has already been said):
${THREAD_CTX}"

  /usr/bin/python3 "$DASH/report.py" --name helm --role Orchestrator --kind orchestrator --status working --task "Working on your request" >/dev/null 2>&1
  timeout 240 claude -p "$FULL_PROMPT" --permission-mode bypassPermissions --model "$MODEL" --max-turns 30 >/dev/null 2>&1
  /usr/bin/python3 "$DASH/report.py" --name helm --role Orchestrator --kind orchestrator --status idle --task "Awaiting orders" >/dev/null 2>&1
}

process

if command -v inotifywait >/dev/null 2>&1; then
  while true; do
    inotifywait -q -t 3600 -e modify,close_write,moved_to "$THREAD" >/dev/null 2>&1
    sleep 0.4
    process
  done
else
  LAST=""
  while true; do
    SIG=$(stat -c "%Y-%s" "$THREAD" 2>/dev/null)
    [ "$SIG" != "$LAST" ] && { LAST="$SIG"; process; }
    sleep 2
  done
fi
