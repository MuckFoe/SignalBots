"""Check and restart existing HouseChoreTracker stack on the server. No deploy/upload."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ssh_config import HOST, PASSWORD, SU, USER  # noqa: E402

import paramiko
COMPOSE_DIR = "/home/signalbot/HouseChoreTracker"


def run(ssh: paramiko.SSHClient, command: str, timeout: int = 180) -> tuple[int, str, str]:
    stdin, stdout, stderr = ssh.exec_command(command, get_pty=True)
    stdout.channel.settimeout(timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return code, out, err


def safe_print(text: str) -> None:
    print(text.encode("ascii", errors="replace").decode("ascii"))


def main() -> None:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {HOST}...")
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)

    for label, command in [
        ("uptime", "uptime"),
        (
            "before",
            SU + '\'docker ps -a --format "{{.Names}} | {{.Status}}"\'',
        ),
    ]:
        code, out, err = run(ssh, command)
        safe_print(f"=== {label} (exit {code}) ===")
        safe_print(out)

    # Ensure Docker starts on boot (no image/code changes).
    run(ssh, SU + "'systemctl enable docker 2>/dev/null; systemctl start docker'")

    # Bring existing stack back up without rebuild.
    start_cmd = (
        SU + ""
        f"'cd {COMPOSE_DIR} && docker compose up -d'"
    )
    code, out, err = run(ssh, start_cmd, timeout=300)
    safe_print(f"=== docker compose up -d (exit {code}) ===")
    safe_print(out)
    if err.strip():
        safe_print(err[-2000:])

    for label, command in [
        (
            "after",
            SU + '\'docker ps -a --format "{{.Names}} | {{.Status}}"\'',
        ),
        ("chore health", "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:5000/health"),
        ("signal health", "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/v1/about"),
        (
            "restart policy",
            f"grep restart {COMPOSE_DIR}/docker-compose.yml 2>/dev/null || echo '(compose file missing)'",
        ),
    ]:
        code, out, err = run(ssh, command)
        safe_print(f"=== {label} (exit {code}) ===")
        safe_print(out.strip())

    ssh.close()
    print("Done.")


if __name__ == "__main__":
    main()
