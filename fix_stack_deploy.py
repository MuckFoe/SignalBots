import paramiko

from ssh_config import HOST, PASSWORD, SU, USER


def run(ssh, command: str, timeout: int = 300) -> tuple[int, str]:
    stdin, stdout, stderr = ssh.exec_command(command, get_pty=True)
    stdout.channel.settimeout(timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return code, out


def main() -> None:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)

    steps = [
        (
            "legacy_down",
            SU + "'cd /home/signalbot/HouseChoreTracker 2>/dev/null && docker compose down || true'",
        ),
        (
            "remove_conflicts",
            SU + "'docker rm -f signal-api chore-bot bot-router rental-bot 2>/dev/null || true'",
        ),
        (
            "up_stack",
            SU + "'cd /home/signalbot/ProjectHub && docker compose up -d'",
        ),
        (
            "ps",
            SU + '\'docker ps --format "{{.Names}} | {{.Status}}"\'',
        ),
        ("router", "curl -s http://127.0.0.1:5100/health"),
        ("chore", "curl -s http://127.0.0.1:5000/health"),
        ("rental", "curl -s http://127.0.0.1:5001/health"),
        (
            "db_counts",
            SU + "'docker run --rm -v housechoretracker_bot-data:/data keinos/sqlite3 sqlite3 /data/chores.db "
            "\"SELECT (SELECT COUNT(*) FROM chores),(SELECT COUNT(*) FROM chore_logs),(SELECT COUNT(*) FROM member_names);\"'",
        ),
        (
            "member_names",
            SU + "'docker run --rm -v housechoretracker_bot-data:/data keinos/sqlite3 sqlite3 /data/chores.db "
            "\"SELECT sender, display_name FROM member_names;\"'",
        ),
    ]

    for label, cmd in steps:
        code, out = run(ssh, cmd, timeout=300)
        print(f"=== {label} (exit {code}) ===")
        print(out.encode("ascii", errors="replace").decode("ascii"))

    ssh.close()


if __name__ == "__main__":
    main()
