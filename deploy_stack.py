import os

import paramiko

from ssh_config import HOST, PASSWORD, REMOTE_ROOT, SU, USER
LOCAL_ROOT = os.path.dirname(os.path.abspath(__file__))

PROJECTS = {
    "HouseChoreTracker": [
        "app.py",
        "commands.py",
        "chart_parse.py",
        "dialogue_utils.py",
        "stats_charts.py",
        "storage.py",
        "schedule_utils.py",
        "vacation_utils.py",
        "bot_registry.py",
        "display_names.py",
        "docker-compose.yml",
        "Dockerfile",
        "requirements.txt",
        "signal_client.py",
    ],
    "HouseRentalTracker": [
        "app.py",
        "commands.py",
        "chart_parse.py",
        "dialogue_utils.py",
        "stats_charts.py",
        "storage.py",
        "scrape_types.py",
        "scrapers.py",
        "poller.py",
        "drive_time.py",
        "utils.py",
        "bot_registry.py",
        "docker-compose.yml",
        "Dockerfile",
        "requirements.txt",
        "signal_client.py",
    ],
    "HouseBotRouter": [
        "app.py",
        "group_router.py",
        "signal_client.py",
        "Dockerfile",
        "requirements.txt",
    ],
    "HouseExpenseTracker": [
        "app.py",
        "commands.py",
        "chart_parse.py",
        "dialogue_utils.py",
        "stats_charts.py",
        "storage.py",
        "balances.py",
        "money.py",
        "display_names.py",
        "bot_registry.py",
        "docker-compose.yml",
        "Dockerfile",
        "requirements.txt",
        "signal_client.py",
    ],
    "HouseGroceryTracker": [
        "app.py",
        "commands.py",
        "storage.py",
        "categories.py",
        "item_parse.py",
        "image_recognition.py",
        "dialogue_utils.py",
        "bot_registry.py",
        "Dockerfile",
        "requirements.txt",
        "signal_client.py",
    ],
}

ROOT_FILES = ["docker-compose.yml", "README.md", ".env.example"]


def run(ssh: paramiko.SSHClient, command: str, timeout: int = 180) -> tuple[int, str, str]:
    stdin, stdout, stderr = ssh.exec_command(command, get_pty=True)
    stdout.channel.settimeout(timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return code, out, err


def ensure_remote_dir(sftp: paramiko.SFTPClient, ssh: paramiko.SSHClient, path: str) -> None:
    try:
        sftp.stat(path)
    except FileNotFoundError:
        run(ssh, f"mkdir -p {path}")


def upload_tree(sftp: paramiko.SFTPClient, ssh: paramiko.SSHClient) -> None:
    ensure_remote_dir(sftp, ssh, REMOTE_ROOT)
    for name in ROOT_FILES:
        local = os.path.join(LOCAL_ROOT, name)
        if os.path.isfile(local):
            remote = f"{REMOTE_ROOT}/{name}"
            sftp.put(local, remote)
            print(f"uploaded {name}")

    for project, files in PROJECTS.items():
        remote_project = f"{REMOTE_ROOT}/{project}"
        ensure_remote_dir(sftp, ssh, remote_project)
        for name in files:
            local = os.path.join(LOCAL_ROOT, project, name)
            remote = f"{remote_project}/{name}"
            sftp.put(local, remote)
            print(f"uploaded {project}/{name}")


def ensure_env(ssh: paramiko.SSHClient) -> None:
    env_path = f"{REMOTE_ROOT}/.env"
    legacy_env = "/home/signalbot/HouseChoreTracker/.env"
    run(
        ssh,
        f"test -f {env_path} || (test -f {legacy_env} && cp {legacy_env} {env_path} || cp {REMOTE_ROOT}/.env.example {env_path} 2>/dev/null || true)",
    )
    for key, value in [
        ("CHORE_BOT_URL", "http://chore-bot:5000"),
        ("RENTAL_BOT_URL", "http://rental-bot:5001"),
        ("EXPENSE_BOT_URL", "http://expense-bot:5002"),
        ("GROCERY_BOT_URL", "http://grocery-bot:5003"),
        ("BOT_PORT", "5100"),
        ("DATABASE_PATH", "/data/router.db"),
    ]:
        run(
            ssh,
            f"grep -q '^{key}=' {env_path} 2>/dev/null || echo '{key}={value}' >> {env_path}",
        )


def main() -> None:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)
    sftp = ssh.open_sftp()

    upload_tree(sftp, ssh)
    sftp.close()

    ensure_env(ssh)

    backup_cmd = (
        SU + ""
        "'docker run --rm -v housechoretracker_bot-data:/data alpine "
        "sh -c \"cp -a /data/chores.db /data/chores.db.bak-$(date +%Y%m%d%H%M%S) && ls -la /data\"'"
    )
    _, backup_out, _ = run(ssh, backup_cmd, timeout=120)
    print("--- db backup ---")
    print(backup_out.encode("ascii", errors="replace").decode("ascii")[-1500:])

    run(
        ssh,
        SU + "'cd /home/signalbot/HouseChoreTracker 2>/dev/null && docker compose down || true; "
        "docker rm -f signal-api chore-bot bot-router rental-bot expense-bot grocery-bot 2>/dev/null || true'",
    )

    deploy_cmd = (
        SU + ""
        f"'cd {REMOTE_ROOT} && docker compose build && docker compose up -d'"
    )
    code, out, err = run(ssh, deploy_cmd, timeout=600)
    print("--- build/up ---")
    safe_out = out.encode("ascii", errors="replace").decode("ascii")
    print(safe_out[-8000:] if len(safe_out) > 8000 else safe_out)
    if err.strip():
        print("--- stderr ---")
        print(err[-2000:] if len(err) > 2000 else err)
    print("exit", code)

    _, ps_out, _ = run(ssh, SU + "'docker ps --format \"{{.Names}} {{.Status}}\"'")
    print("--- containers ---")
    print(ps_out)

    for label, url in [
        ("router", "http://127.0.0.1:5100/health"),
        ("chore", "http://127.0.0.1:5000/health"),
        ("rental", "http://127.0.0.1:5001/health"),
        ("expense", "http://127.0.0.1:5002/health"),
        ("grocery", "http://127.0.0.1:5003/health"),
    ]:
        _, health_out, _ = run(ssh, f"curl -s -o /dev/null -w '%{{http_code}}' {url}")
        print(f"health {label}", health_out.strip())

    ssh.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)
        for label, command in [
            ("containers", SU + '\'docker ps --format "{{.Names}} {{.Status}}"\''),
            ("router", "curl -s http://127.0.0.1:5100/health"),
            ("chore", "curl -s http://127.0.0.1:5000/health"),
            ("rental", "curl -s http://127.0.0.1:5001/health"),
            ("expense", "curl -s http://127.0.0.1:5002/health"),
            ("grocery", "curl -s http://127.0.0.1:5003/health"),
            ("router-logs", SU + "'docker logs bot-router --tail 15'"),
            ("chore-logs", SU + "'docker logs chore-bot --tail 15'"),
        ]:
            code, out, err = run(ssh, command)
            print(f"=== {label} (exit {code}) ===")
            print(out.encode("ascii", errors="replace").decode("ascii"))
        ssh.close()
    else:
        main()
