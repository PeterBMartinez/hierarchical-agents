Show recent logs for agent services on pi-02.

$ARGUMENTS can be: helm, atlas, ops, net, dashboard, or empty (shows all).

Service name mapping:
- "helm" → helm-watcher
- "atlas" → atlas-watcher
- "ops" → ops-watcher
- "net" → net-watcher
- "dashboard" → agent-dashboard
- empty → all five services

If a specific agent was named, run:
```
ssh peter@100.99.6.88 "journalctl -u <service-name> -n 60 --no-pager"
```

If no argument, run:
```
ssh peter@100.99.6.88 "journalctl -u agent-dashboard -u helm-watcher -u ops-watcher -u atlas-watcher -u net-watcher -n 20 --no-pager"
```

Also show the agent's progress log if one exists:
```
ssh peter@100.99.6.88 "tail -20 /home/peter/hierarchical-agents/dashboard/state/logs/<agent>.jsonl 2>/dev/null"
```

Summarize: what the agent last did, whether it completed successfully, and any errors visible in the logs.
