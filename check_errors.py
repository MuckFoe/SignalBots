import paramiko

from deploy_stack import run
from ssh_config import HOST, PASSWORD, SU, USER

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)

cmds = [
    ("chore-errors", SU + "'docker logs chore-bot 2>&1 | grep -iE \"error|traceback|exception|failed\" | tail -30'"),
    ("rental-errors", SU + "'docker logs rental-bot 2>&1 | grep -iE \"error|traceback|exception|failed\" | tail -30'"),
    ("router-errors-all", SU + "'docker logs bot-router 2>&1 | grep -iE \"error|traceback|exception|failed|500\" | tail -40'"),
    ("signal-errors", SU + "'docker logs signal-api 2>&1 | grep -iE \"error|failed\" | tail -20'"),
]

for label, cmd in cmds:
    _, out, _ = run(ssh, cmd)
    print(f"=== {label} ===")
    print(out.encode("ascii", errors="replace").decode() or "(none)")
    print()

ssh.close()
