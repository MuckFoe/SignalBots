import paramiko

from ssh_config import HOST, PASSWORD, SU, USER

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)

cmds = [
    SU + "'docker logs bot-router 2>&1 | grep -i \"Failed\\|ERROR\\|chore\" | tail -50'",
    SU + "'docker logs chore-bot 2>&1 | grep -iE \"Failed|ERROR|Exception|Traceback\" | tail -30'",
    SU + "'sqlite3 /home/signalbot/ProjectHub/HouseChoreTracker/chores.db \"SELECT scope_id FROM chat_admins LIMIT 3;\" 2>/dev/null || docker exec chore-bot sqlite3 /data/chores.db \"SELECT scope_id FROM chat_admins LIMIT 3;\" 2>&1'",
]
for cmd in cmds:
    stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    print(f"=== {cmd[40:90]} ===")
    print(out)
ssh.close()
