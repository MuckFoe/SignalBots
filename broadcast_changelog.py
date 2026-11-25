"""Send the latest CHANGELOG.md message to every chat that uses a bot: groups and direct chats.

    python broadcast_changelog.py          # dry run: list targets and texts
    python broadcast_changelog.py --send   # actually send
    python broadcast_changelog.py --only chores [--send]   # one bot's chats only
                                           # (e.g. adding a block to an already-sent release)

Each chat gets the block for its bot and language (```chores-de``` etc., first
occurrence in CHANGELOG.md = latest release). A chat counts as using a bot if
that bot has settings for it: a group once set up (it has an admin), a direct
chat once it has written to the bot. The router decides which bot that is now:
a chat switched to another bot, or moved to another platform, only gets news of
the bot it uses today. Signal groups are only targeted if the bot is still a
member.
"""

import base64
import json
import re
import sys
import time
from pathlib import Path

import paramiko

from deploy_stack import run
from ssh_config import HOST, PASSWORD, REMOTE_ROOT, SU, USER

BOT_NUMBER = "+4915206685988"
CONTAINERS = {"chores": "chore-bot", "rentals": "rental-bot", "expenses": "expense-bot"}
CHAT_QUERY = """
import os, sqlite3
c = sqlite3.connect(os.environ['DATABASE_PATH'])
admins = {r[0] for r in c.execute('SELECT DISTINCT scope_id FROM chat_admins')}
for scope_id, language in c.execute("SELECT scope_id, language FROM chat_settings"):
    if scope_id.startswith('dm:') or (scope_id.startswith('group:') and scope_id in admins):
        print(scope_id + '\\t' + (language or 'en'))
"""
# The router's view: which bot each chat uses now, and which chats have moved away.
ROUTER_QUERY = """
import os, sqlite3
c = sqlite3.connect(os.environ['DATABASE_PATH'])
for scope_id, job in c.execute('SELECT scope_id, job FROM group_jobs'):
    print('job\\t' + scope_id + '\\t' + job)
for (scope_id,) in c.execute('SELECT scope_id FROM moved_scopes'):
    print('moved\\t' + scope_id)
"""


def latest_messages() -> dict[str, str]:
    text = Path(__file__).with_name("CHANGELOG.md").read_text(encoding="utf-8")
    # Only the newest "## " release: a bot without news there gets nothing,
    # rather than an older release's message a second time.
    latest = re.split(r"(?m)^## ", text)[1]
    return {
        tag: body.strip()
        for tag, body in re.findall(r"```([a-z]+-[a-z]{2})\n(.*?)\n```", latest, flags=re.S)
    }


def remote_python(ssh: paramiko.SSHClient, container: str, source: str) -> str:
    encoded = base64.b64encode(source.encode()).decode()
    _, out, _ = run(ssh, SU + f"'echo {encoded} | base64 -d | docker exec -i {container} python -'")
    return out.replace("Password:", "").strip()


def signal_member_groups(ssh: paramiko.SSHClient) -> set[str]:
    _, out, _ = run(ssh, f"curl -s http://127.0.0.1:8080/v1/groups/{BOT_NUMBER}")
    return {group["internal_id"] for group in json.loads(out) if group.get("members")}


def router_view(ssh: paramiko.SSHClient) -> tuple[dict[str, str], set[str]]:
    jobs: dict[str, str] = {}
    moved: set[str] = set()
    for line in remote_python(ssh, "bot-router", ROUTER_QUERY).splitlines():
        parts = line.split("\t")
        if parts[0] == "job" and len(parts) == 3:
            jobs[parts[1]] = parts[2]
        elif parts[0] == "moved" and len(parts) == 2:
            moved.add(parts[1])
    return jobs, moved


def send(ssh: paramiko.SSHClient, scope_id: str, message: str) -> str:
    is_group = scope_id.startswith("group:")
    chat_id = scope_id.split(":", 1)[1]
    if "@" in chat_id:
        url = "http://127.0.0.1:3000/api/sendText"
        payload = {"session": "default", "chatId": chat_id, "text": message}
        auth = f"-H \"X-Api-Key: $(grep ^WHATSAPP_API_KEY= {REMOTE_ROOT}/.env | cut -d= -f2)\" "
    else:
        url = "http://127.0.0.1:8080/v2/send"
        recipient = "group." + base64.b64encode(chat_id.encode()).decode() if is_group else chat_id
        payload = {"message": message, "number": BOT_NUMBER, "recipients": [recipient]}
        auth = ""
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    _, out, _ = run(
        ssh,
        f"echo {encoded} | base64 -d | curl -s -o /dev/null -w '%{{http_code}}' -X POST {url} "
        f"-H 'Content-Type: application/json' {auth}--data-binary @-",
    )
    return out.strip()


def main() -> None:
    really_send = "--send" in sys.argv
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    if only is not None and only not in CONTAINERS:
        sys.exit(f"--only must be one of {', '.join(CONTAINERS)}")
    messages = latest_messages()
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)
    signal_groups = signal_member_groups(ssh)
    current_job, moved = router_view(ssh)

    targets = []
    for job, container in CONTAINERS.items():
        if only and job != only:
            continue
        for line in remote_python(ssh, container, CHAT_QUERY).splitlines():
            if "\t" not in line:
                continue
            scope_id, language = line.split("\t")
            chat_id = scope_id.split(":", 1)[1]
            if scope_id in moved:
                print(f"skip {scope_id} ({job}): moved to another platform")
                continue
            if current_job.get(scope_id, job) != job:
                print(f"skip {scope_id} ({job}): now uses {current_job[scope_id]}")
                continue
            if scope_id.startswith("group:") and "@" not in chat_id and chat_id not in signal_groups:
                print(f"skip {scope_id} ({job}): bot is no longer in this Signal group")
                continue
            tag = f"{job}-{language}"
            if tag not in messages:
                print(f"skip {scope_id}: no ```{tag}``` block in CHANGELOG.md")
                continue
            targets.append((job, language, scope_id, messages[tag]))

    for job, language, scope_id, message in targets:
        print(f"\n=== {job} / {language} / {scope_id}")
        if really_send:
            print("sent, HTTP", send(ssh, scope_id, message))
            time.sleep(2)
        else:
            print(message)
    if not really_send:
        groups = sum(1 for target in targets if target[2].startswith("group:"))
        print(f"\nDry run: {groups} group(s), {len(targets) - groups} direct chat(s). Add --send to send.")
    ssh.close()


if __name__ == "__main__":
    main()
