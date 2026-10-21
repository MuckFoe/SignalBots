"""Send the latest CHANGELOG.md group message to every set-up group.

    python broadcast_changelog.py          # dry run: list targets and texts
    python broadcast_changelog.py --send   # actually send

Each group gets the block for its bot and language (```chores-de``` etc.,
first occurrence in CHANGELOG.md = latest release). Signal groups are only
targeted if the bot is still a member.
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
GROUP_QUERY = """
import os, sqlite3
c = sqlite3.connect(os.environ['DATABASE_PATH'])
admins = {r[0] for r in c.execute('SELECT DISTINCT scope_id FROM chat_admins')}
for scope_id, language in c.execute("SELECT scope_id, language FROM chat_settings WHERE scope_id LIKE 'group:%'"):
    if scope_id in admins:
        print(scope_id + '\\t' + (language or 'en'))
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


def send(ssh: paramiko.SSHClient, group_id: str, message: str) -> str:
    if "@" in group_id:
        url = "http://127.0.0.1:3000/api/sendText"
        payload = {"session": "default", "chatId": group_id, "text": message}
        auth = f"-H \"X-Api-Key: $(grep ^WHATSAPP_API_KEY= {REMOTE_ROOT}/.env | cut -d= -f2)\" "
    else:
        url = "http://127.0.0.1:8080/v2/send"
        recipient = "group." + base64.b64encode(group_id.encode()).decode()
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
    messages = latest_messages()
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)
    signal_groups = signal_member_groups(ssh)

    targets = []
    for job, container in CONTAINERS.items():
        for line in remote_python(ssh, container, GROUP_QUERY).splitlines():
            scope_id, language = line.split("\t")
            group_id = scope_id.removeprefix("group:")
            if "@" not in group_id and group_id not in signal_groups:
                print(f"skip {scope_id} ({job}): bot is no longer in this Signal group")
                continue
            tag = f"{job}-{language}"
            if tag not in messages:
                print(f"skip {scope_id}: no ```{tag}``` block in CHANGELOG.md")
                continue
            targets.append((job, language, group_id, messages[tag]))

    for job, language, group_id, message in targets:
        print(f"\n=== {job} / {language} / {group_id}")
        if really_send:
            print("sent, HTTP", send(ssh, group_id, message))
            time.sleep(2)
        else:
            print(message)
    if not really_send:
        print(f"\nDry run: {len(targets)} group(s). Add --send to send.")
    ssh.close()


if __name__ == "__main__":
    main()
