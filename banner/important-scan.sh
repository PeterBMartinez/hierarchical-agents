#!/usr/bin/env bash
export HOME=/home/peter
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
cd /home/peter/hierarchical-agents/banner
mkdir -p runs
TS=$(date +%F_%H%M)
timeout 420 claude -p "$(cat important-prompt.txt)" --permission-mode bypassPermissions --model sonnet --max-turns 40 --output-format json > "runs/$TS.json" 2>"runs/$TS.err"
python3 - "$TS" <<"PY"
import sys, json
ts = sys.argv[1]
try:
    d = json.load(open(f"runs/{ts}.json"))
    cost = d.get("total_cost_usd", d.get("cost_usd"))
    with open("cost.log", "a") as f:
        f.write(f"{ts}\tcost_usd={cost}\n")
    print(f"important-scan done {ts} cost_usd={cost}")
except Exception as e:
    print("parse error:", e)
PY
