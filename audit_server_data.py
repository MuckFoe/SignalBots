"""Pre-deploy audit: verify chore data volumes and DB on server without changing anything."""

import paramiko

from ssh_config import HOST, PASSWORD, SU, USER


def run(ssh, command: str, timeout: int = 120) -> tuple[int, str]:
    stdin, stdout, stderr = ssh.exec_command(command, get_pty=True)
    stdout.channel.settimeout(timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return code, out


def main() -> None:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)

    checks = [
        (
            "volumes",
            SU + "'docker volume ls | grep -E \"housechoretracker|projecthub\"'",
        ),
        (
            "chore_db_files",
            SU + "'docker run --rm -v housechoretracker_bot-data:/data alpine ls -la /data'",
        ),
        (
            "chore_db_counts",
            SU + "'docker run --rm -v housechoretracker_bot-data:/data keinos/sqlite3 sqlite3 /data/chores.db "
            "\"SELECT (SELECT COUNT(*) FROM chores) AS chores, "
            "(SELECT COUNT(*) FROM chore_logs) AS logs, "
            "(SELECT COUNT(*) FROM chat_admins) AS admins, "
            "(SELECT COUNT(*) FROM chat_settings) AS settings;\"' 2>&1 || "
            "docker run --rm -v housechoretracker_bot-data:/data alpine sh -c '"
            "apk add --no-cache sqlite >/dev/null 2>&1; sqlite3 /data/chores.db "
            "\"SELECT (SELECT COUNT(*) FROM chores) AS chores, "
            "(SELECT COUNT(*) FROM chore_logs) AS logs, "
            "(SELECT COUNT(*) FROM chat_admins) AS admins, "
            "(SELECT COUNT(*) FROM chat_settings) AS settings;\"'",
        ),
        (
            "distinct_senders",
            SU + "'docker run --rm -v housechoretracker_bot-data:/data alpine sh -c \""
            "apk add --no-cache sqlite >/dev/null 2>&1; sqlite3 /data/chores.db "
            "\\\"SELECT sender, COUNT(*) FROM chore_logs GROUP BY sender ORDER BY COUNT(*) DESC LIMIT 10;\\\"\"'",
        ),
        (
            "signal_volume",
            SU + "'docker volume inspect housechoretracker_signal-cli-config --format \"{{.Mountpoint}}\"'",
        ),
        (
            "compose_volume_mapping",
            "grep -A2 'bot-data' /home/signalbot/ProjectHub/docker-compose.yml 2>/dev/null || echo 'ProjectHub compose not on server yet'",
        ),
    ]

    for label, cmd in checks:
        code, out = run(ssh, cmd, timeout=180)
        print(f"=== {label} (exit {code}) ===")
        print(out.encode("ascii", errors="replace").decode("ascii"))

    ssh.close()


if __name__ == "__main__":
    main()
