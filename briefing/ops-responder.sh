#!/usr/bin/env bash
export HOME=/home/peter
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export AGENT_STATE_DIR=/home/peter/hierarchical-agents/dashboard/state
DASH=/home/peter/hierarchical-agents/dashboard
cd /home/peter/hierarchical-agents/briefing
exec 9>/tmp/ops-responder.lock
flock -n 9 || exit 0
PENDING=$(/usr/bin/python3 "$DASH/hermit_chat.py" inbox --name ops 2>/dev/null)
[ -z "$PENDING" ] && exit 0
[ "$PENDING" = "(no new messages)" ] && exit 0
MODEL=$(/usr/bin/python3 -c "import json,os;p=os.path.join('$AGENT_STATE_DIR','models.json');d=json.load(open(p)) if os.path.isfile(p) else {};print(d.get('ops') or 'sonnet')" 2>/dev/null); [ -z "$MODEL" ] && MODEL=sonnet

read -r -d '' OPS_PROMPT <<'EOF'
You are ops, the delivery coordinator on the mission dashboard. Answer the pending message(s) from the user.
1. Read the inbox: /usr/bin/python3 /home/peter/hierarchical-agents/dashboard/hermit_chat.py inbox --name ops
2. Answer concisely and helpfully, using READ-ONLY connector data when relevant. Projects you cover: Aria — Peter's ONLY Aria responsibility is reviewing pull requests in the Aria_v2_Frontend and Aria_v2_Backend repos (Azure DevOps org ariagpo, project Member Portal); ignore other Aria repos and work items. TruckSpy (ClickUp space TruckSpy | Scope), Warp 9 (ClickUp space Warp 9 | Scope), plus Teams and Outlook comms. If asked to re-run the briefing, run /bin/bash /home/peter/hierarchical-agents/briefing/run-briefing.sh and say it is running.
Peter has a Delivery To-Do board (data source collection://0fff06e2-62de-4d1f-80e4-b75e25e50fc6). Use these Notion tool calls:
  READ all cards: notion-search { "query": "review reply PR task brief", "data_source_url": "collection://0fff06e2-62de-4d1f-80e4-b75e25e50fc6", "page_size": 25, "content_search_mode": "workspace_search" }
  MARK Done: notion-update-page { "page_id": "<card id>", "command": "update_properties", "properties": { "Status": "Done" } } — only with concrete evidence (PR merged, task closed, reply sent).
  ADD card: notion-create-pages { "parent": { "type": "data_source_id", "data_source_id": "0fff06e2-62de-4d1f-80e4-b75e25e50fc6" }, "pages": [{ "properties": { "Task": "...", "Status": "Todo", "Project": "...", "Priority": "...", "Source": "..." } }] } — only for items not already on the board in ANY status.
  Never delete cards, never change any field other than Status→Done, never move a card backward.
3. Post your reply by running: /usr/bin/python3 /home/peter/hierarchical-agents/dashboard/hermit_chat.py reply --name ops --text "YOUR ANSWER"
Do NOT send emails or Teams messages or modify ClickUp or Azure DevOps. Reply only.
EOF

THREAD_CTX=$(/usr/bin/python3 - <<'PYEOF'
import json, os
base = '/home/peter/hierarchical-agents/dashboard/state/threads'
try:
    idx = os.path.join(base, 'ops', 'index.json')
    conv_id = None
    if os.path.isfile(idx):
        for c in json.load(open(idx)):
            if c.get('active'):
                conv_id = c['id']; break
    path = os.path.join(base, 'ops', conv_id+'.jsonl') if conv_id else os.path.join(base, 'ops.jsonl')
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

FULL_PROMPT="${OPS_PROMPT}

RECENT CONVERSATION HISTORY (last 10 messages — use this for context on what has already been said):
${THREAD_CTX}"

/usr/bin/python3 "$DASH/report.py" --name ops --role "Delivery Coordinator" --kind ops --status working --task "Answering your message" >/dev/null 2>&1
timeout 240 claude -p "$FULL_PROMPT" --permission-mode bypassPermissions --model "$MODEL" --max-turns 30 >/dev/null 2>&1
/usr/bin/python3 "$DASH/report.py" --name ops --role "Delivery Coordinator" --kind ops --status idle --task "Awaiting requests" >/dev/null 2>&1
