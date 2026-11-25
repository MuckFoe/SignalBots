"""Deploy the stack to the VM.

    python deploy_stack.py           # upload, back up every database, rebuild and start
    python deploy_stack.py verify    # read-only: containers, health, recent logs
    python deploy_stack.py files     # local only: list what a deploy would upload
"""

import os
import sys
from datetime import datetime

import paramiko

from ssh_config import HOST, PASSWORD, REMOTE_ROOT, SU, USER
LOCAL_ROOT = os.path.dirname(os.path.abspath(__file__))

# Every bot directory is uploaded whole (spec 009 FR4), so a new module ships without touching this
# file. Left out: tests, caches, local secrets and databases, and anything a container never needs.
PROJECTS = ["HouseChoreTracker", "HouseRentalTracker", "HouseBotRouter", "HouseExpenseTracker"]
SKIP_DIRS = {"__pycache__", ".venv", "venv", ".pytest_cache", ".mypy_cache"}
SKIP_FILES = {".env", ".DS_Store"}


def _skip_file(name: str) -> bool:
    return (
        name in SKIP_FILES
        or name.startswith("test_")
        or name.endswith((".pyc", ".tmp", ".log"))
        or ".db" in name  # chores.db, chores.db-journal, chores.db.bak-…
    )


def upload_files() -> list[str]:
    """Paths (relative to the repo root, with "/") that a deploy uploads, in a stable order."""
    files = list(ROOT_FILES)
    for project in PROJECTS:
        base = os.path.join(LOCAL_ROOT, project)
        for folder, dirs, names in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
            for name in sorted(names):
                if _skip_file(name):
                    continue
                rel = os.path.relpath(os.path.join(folder, name), LOCAL_ROOT)
                files.append(rel.replace(os.sep, "/"))
    return [name for name in files if os.path.isfile(os.path.join(LOCAL_ROOT, name))]


# Volume -> database file inside it. Backed up before the stack goes down (spec 009 FR4).
DATABASES = [
    ("housechoretracker_bot-data", "chores.db"),
    ("rental-bot-data", "rentals.db"),
    ("router-data", "router.db"),
    ("expense-bot-data", "expenses.db"),
]


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
    made: set[str] = set()
    for name in upload_files():
        remote_dir = f"{REMOTE_ROOT}/{os.path.dirname(name)}".rstrip("/")
        if remote_dir not in made:
            ensure_remote_dir(sftp, ssh, remote_dir)
            made.add(remote_dir)
        sftp.put(os.path.join(LOCAL_ROOT, *name.split("/")), f"{REMOTE_ROOT}/{name}")
        print(f"uploaded {name}")


CONTAINERS = ["signal-api", "whatsapp-api", "bot-router", "chore-bot", "rental-bot", "expense-bot"]


def _print_tail(label: str, out: str, err: str, code: int) -> None:
    safe_out = out.encode("ascii", errors="replace").decode("ascii")
    print(f"--- {label} ---")
    print(safe_out[-4000:])
    if err.strip():
        print("--- stderr ---")
        print(err[-2000:])
    print("exit", code, flush=True)


def backup_command(stamp: str) -> str:
    """One throwaway container mounts every bot volume and copies each database under one timestamp.

    No "$" in here: the command passes through two shells (su, then sh in the container)."""
    mounts = " ".join(f"-v {volume}:/b{index}" for index, (volume, _) in enumerate(DATABASES))
    copies = "; ".join(
        f"if [ -f /b{index}/{db} ]; then cp -a /b{index}/{db} /b{index}/{db}.bak-{stamp} && echo backed up {db} || exit 1; "
        f"else echo no {db}; fi"
        for index, (_, db) in enumerate(DATABASES)
    )
    return SU + f"'docker run --rm {mounts} alpine sh -c \"{copies}\"'"


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
        ("BOT_PORT", "5100"),
        ("DATABASE_PATH", "/data/router.db"),
    ]:
        run(
            ssh,
            f"grep -q '^{key}=' {env_path} 2>/dev/null || echo '{key}={value}' >> {env_path}",
        )
    # whatsapp-api refuses to start without a key; generate one on first deploy.
    run(
        ssh,
        f"grep -q '^WHATSAPP_API_KEY=' {env_path} 2>/dev/null || "
        f"echo \"WHATSAPP_API_KEY=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \\n')\" >> {env_path}",
    )


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)  # progress shows up even when piped to a file
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)
    sftp = ssh.open_sftp()

    upload_tree(sftp, ssh)
    sftp.close()

    ensure_env(ssh)

    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    code, backup_out, _ = run(ssh, backup_command(stamp), timeout=120)
    print("--- db backup ---")
    print(backup_out.encode("ascii", errors="replace").decode("ascii")[-1500:])
    if code != 0:
        # Never touch the stack without a backup.
        raise SystemExit(f"Backup failed (exit {code}); nothing was changed.")

    # Build while the old containers keep answering; a failed build leaves the stack as it was.
    code, out, err = run(ssh, SU + f"'cd {REMOTE_ROOT} && docker compose build'", timeout=1800)
    _print_tail("build", out, err, code)
    if code != 0:
        raise SystemExit(f"Build failed (exit {code}); the running stack was left as it was.")

    # Recreates only the containers whose image or config changed: seconds of downtime, and
    # signal-api / whatsapp-api (and with them the messenger links) keep running.
    code, out, err = run(ssh, SU + f"'cd {REMOTE_ROOT} && docker compose up -d --remove-orphans'", timeout=300)
    _print_tail("up", out, err, code)
    if code != 0:
        # A container with the same name from an older compose project blocks "up". Clear it once.
        print("up failed; removing stale containers and trying again")
        run(ssh, SU + f"'docker rm -f {' '.join(CONTAINERS)} 2>/dev/null || true'")
        code, out, err = run(ssh, SU + f"'cd {REMOTE_ROOT} && docker compose up -d --remove-orphans'", timeout=300)
        _print_tail("up (retry)", out, err, code)

    _, ps_out, _ = run(ssh, SU + "'docker ps --format \"{{.Names}} {{.Status}}\"'")
    print("--- containers ---")
    print(ps_out)

    for label, url in [
        ("router", "http://127.0.0.1:5100/health"),
        ("chore", "http://127.0.0.1:5000/health"),
        ("rental", "http://127.0.0.1:5001/health"),
        ("expense", "http://127.0.0.1:5002/health"),
    ]:
        _, health_out, _ = run(ssh, f"curl -s -o /dev/null -w '%{{http_code}}' {url}")
        print(f"health {label}", health_out.strip())

    ssh.close()


if __name__ == "__main__":

    if len(sys.argv) > 1 and sys.argv[1] == "files":
        # Local only: what a deploy would upload.
        print("\n".join(upload_files()))
    elif len(sys.argv) > 1 and sys.argv[1] == "verify":
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)
        for label, command in [
            ("containers", SU + '\'docker ps --format "{{.Names}} {{.Status}}"\''),
            ("router", "curl -s http://127.0.0.1:5100/health"),
            ("chore", "curl -s http://127.0.0.1:5000/health"),
            ("rental", "curl -s http://127.0.0.1:5001/health"),
            ("expense", "curl -s http://127.0.0.1:5002/health"),
            ("router-logs", SU + "'docker logs bot-router --tail 15'"),
            ("chore-logs", SU + "'docker logs chore-bot --tail 15'"),
        ]:
            code, out, err = run(ssh, command)
            print(f"=== {label} (exit {code}) ===")
            print(out.encode("ascii", errors="replace").decode("ascii"))
        ssh.close()
    else:
        main()
