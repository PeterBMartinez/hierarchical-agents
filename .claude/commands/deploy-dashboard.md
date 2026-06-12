Deploy changed dashboard files to pi-02 and restart services.

1. Identify which dashboard files have changed since the last deploy (check git diff or ask the user if unclear).
2. SCP the changed files to pi-02:
   ```
   scp <files> peter@100.99.6.88:/home/peter/hierarchical-agents/dashboard/
   ```
   Common targets: `dashboard/server.py`, `dashboard/mission-control.dc.html`, `dashboard/parse_stream.py`, `dashboard/hermit_chat.py`
3. If `server.py` or `mission-control.dc.html` changed, restart the dashboard:
   ```
   ssh peter@100.99.6.88 "sudo systemctl restart agent-dashboard"
   ```
4. If a watcher script changed (helm/ops/atlas/net-watcher.sh), restart that watcher:
   ```
   ssh peter@100.99.6.88 "sudo systemctl restart <name>-watcher"
   ```
5. Confirm each restarted service is active:
   ```
   ssh peter@100.99.6.88 "sudo systemctl is-active agent-dashboard helm-watcher ops-watcher atlas-watcher net-watcher"
   ```
6. Report: which files were deployed, which services were restarted, and active/inactive status for each.
