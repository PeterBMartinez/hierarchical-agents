Check the status of all agent services on pi-02.

Run:
```
ssh peter@100.99.6.88 "sudo systemctl status agent-dashboard helm-watcher ops-watcher atlas-watcher net-watcher --no-pager -l 2>&1 | head -80"
```

Report for each service:
- Whether it is active (running) or failed/inactive
- If failed: show the last 5 log lines and the most recent error
- If all active: confirm everything is healthy

Also show the current agent state by fetching:
```
ssh peter@100.99.6.88 "cat /home/peter/hierarchical-agents/dashboard/state/agents/*.json 2>/dev/null | python3 -c \"import sys,json; [print(json.load(open('/home/peter/hierarchical-agents/dashboard/state/agents/'+n+'.json')).get('name','?'),'→',json.load(open('/home/peter/hierarchical-agents/dashboard/state/agents/'+n+'.json')).get('status','?')) for n in ['helm','atlas','ops','net']]\" 2>/dev/null || echo 'state unavailable'"
```
