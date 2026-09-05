import json
import time

import paramiko

from deploy_stack import run
from ssh_config import HOST, PASSWORD, SU, TEST_SENDER, USER

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)
time.sleep(5)

checks = [
    ("chore-health", "curl -s -w ' code=%{http_code}' http://127.0.0.1:5000/health"),
    ("rental-health", "curl -s -w ' code=%{http_code}' http://127.0.0.1:5001/health"),
    ("chore-logs", SU + "'docker logs chore-bot --tail 50 2>&1'"),
    ("rental-logs", SU + "'docker logs rental-bot --tail 50 2>&1'"),
    ("router-errors", SU + "'docker logs bot-router --tail 80 2>&1 | grep -iE error || true'"),
]

payload = json.dumps({
    "scope_id": "group:testgrp",
    "sender": TEST_SENDER,
    "message": "help",
    "group_id": "testgrp",
})
checks.append(
    ("chore-help", f"curl -s -X POST http://127.0.0.1:5000/internal/handle -H 'Content-Type: application/json' -d '{payload}'")
)
payload = json.dumps({
    "scope_id": "group:smoketest",
    "sender": TEST_SENDER,
    "message": "hilfe",
    "group_id": "smoketest",
})
checks.append(("rental-hilfe", f"curl -s -w ' code=%{{http_code}}' -X POST http://127.0.0.1:5001/internal/handle -H 'Content-Type: application/json' -d '{payload}'"))
chart_payload = json.dumps({
    "scope_id": "group:testgrp",
    "sender": TEST_SENDER,
    "message": "gruppen statistik diagramm",
    "group_id": "testgrp",
})
checks.append(
    ("chore-chart", f"curl -s -X POST http://127.0.0.1:5000/internal/handle -H 'Content-Type: application/json' -d '{chart_payload}'")
)
checks.append(
    ("router-recent", SU + "'docker logs bot-router --tail 120 2>&1'")
)

for label, cmd in checks:
    _, out, _ = run(ssh, cmd)
    print(f"=== {label} ===")
    print(out.encode("ascii", errors="replace").decode())
    print()

ssh.close()
