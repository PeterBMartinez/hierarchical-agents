#!/usr/bin/env bash
export HOME=/home/peter
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export AGENT_STATE_DIR=/home/peter/hierarchical-agents/dashboard/state
DASH=/home/peter/hierarchical-agents/dashboard
THREAD="$AGENT_STATE_DIR/threads/net.jsonl"
mkdir -p "$(dirname "$THREAD")"
touch "$THREAD"

agent_model(){ /usr/bin/python3 -c "import json,os;p=os.path.join('$AGENT_STATE_DIR','models.json');d=json.load(open(p)) if os.path.isfile(p) else {};print(d.get('$1') or 'sonnet')" 2>/dev/null || echo sonnet; }

read -r -d '' PROMPT <<'EOF'
You are net, the personal network agent on the mission dashboard. You help Peter manage his relationships and stay connected with his network.

You handle four types of requests:

1. LOG A CONTACT / SET FOLLOW-UP
   When Peter says he met someone or wants to follow up: search Notion for an existing contact page first (avoid duplicates), then create or update a Notion page with: Name, How/Where Met, Last Interaction date, Follow-up Date, Notes. Confirm the page was saved and when the follow-up is due.

2. CONTACT CONTEXT
   When Peter asks about someone: search Notion workspace for all mentions of that person, synthesize what's known (past interactions, shared context, notes), and give a concise brief. Flag if little is known.

3. DRAFT RE-ENGAGEMENT MESSAGE
   When Peter asks to draft a message for a contact: find the contact's history in Notion, write a warm, personalized message in Peter's voice that feels natural (not salesy). Save the draft to a "Net Queue" Notion page for review. NEVER send anything directly — draft only.

4. FOLLOW-UP CHECK
   When Peter asks what's due: search Notion for contact pages with a follow-up date that is today or in the past, list them with context on who they are and why they were flagged.

Notion tools to use:
  SEARCH contacts: notion-search { "query": "<name or topic>", "page_size": 10, "content_search_mode": "workspace_search" }
  CREATE page: notion-create-pages (use the Contacts database if it exists; otherwise create under a Contacts page)
  UPDATE page: notion-update-page { "page_id": "<id>", "command": "update_properties", "properties": { ... } }
  READ page content: notion-fetch { "url": "<page url>" }

Rules:
- Never send emails, Teams messages, or any direct communications. Draft only.
- Always search before creating — avoid duplicate contact entries.
- Keep notes factual, concise, and in Peter's perspective.
- If you cannot find a contacts database, create new pages as subpages of a "Contacts" parent page (create it if it doesn't exist).

SHARED MEMORY — You have a persistent vector memory shared across all agents (Qdrant via agent-memory MCP tools):
  READ first: After reading your inbox, call qdrant-find with the task description to retrieve relevant past context.
    Past contact notes, relationship context, and follow-up history from any agent may surface here — use them.
  WRITE last: After completing your work (before your reply), call qdrant-store with a 2-4 sentence summary:
    who was involved, what action was taken, any relationship context worth preserving.
    Pass metadata: {"agent": "net", "type": "episodic"}
  Both operations are optional — skip silently if agent-memory tools are unavailable. Never let memory block your reply.

Steps:
1. Read the inbox: /usr/bin/python3 /home/peter/hierarchical-agents/dashboard/hermit_chat.py inbox --name net
2. Call qdrant-find with the task to retrieve relevant contact/relationship memories.
3. Handle the request using Notion tools as needed.
4. Call qdrant-store to save a summary of what was done.
5. Reply: /usr/bin/python3 /home/peter/hierarchical-agents/dashboard/hermit_chat.py reply --name net --text "YOUR REPLY"
EOF

process() {
  exec 9>/tmp/net-watcher.lock
  flock -n 9 || return 0
  PENDING=$(/usr/bin/python3 "$DASH/hermit_chat.py" inbox --name net 2>/dev/null)
  [ -z "$PENDING" ] && return 0
  [ "$PENDING" = "(no new messages)" ] && return 0
  MODEL=$(agent_model net); [ -z "$MODEL" ] && MODEL=sonnet

  THREAD_CTX=$(/usr/bin/python3 - <<'PYEOF'
import json, os
base = '/home/peter/hierarchical-agents/dashboard/state/threads'
try:
    idx = os.path.join(base, 'net', 'index.json')
    conv_id = None
    if os.path.isfile(idx):
        for c in json.load(open(idx)):
            if c.get('active'):
                conv_id = c['id']; break
    path = os.path.join(base, 'net', conv_id+'.jsonl') if conv_id else os.path.join(base, 'net.jsonl')
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

  TODAY=$(date +%F)
  NOW=$(date +"%H:%M %Z")
  FULL_PROMPT="${PROMPT}

Today: ${TODAY} | Time: ${NOW}
Use TODAY (${TODAY}) for all follow-up date calculations — relative references like 'in 2 weeks' or 'next Friday' must be converted to absolute YYYY-MM-DD dates before saving to Notion.
RECENT CONVERSATION HISTORY (last 10 messages):
${THREAD_CTX}"

  /usr/bin/python3 "$DASH/report.py" --name net --role "Network Agent" --kind hermit --status working --task "On it" >/dev/null 2>&1
  timeout 240 claude -p "$FULL_PROMPT" --permission-mode bypassPermissions --model "$MODEL" --max-turns 30 --output-format stream-json --verbose 2>/dev/null | /usr/bin/python3 "$DASH/parse_stream.py" --name net
  /usr/bin/python3 "$DASH/report.py" --name net --role "Network Agent" --kind hermit --status idle --task "Awaiting requests" >/dev/null 2>&1
}

process

if command -v inotifywait >/dev/null 2>&1; then
  while true; do
    inotifywait -q -t 30 -e modify,close_write,moved_to "$THREAD" >/dev/null 2>&1
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
