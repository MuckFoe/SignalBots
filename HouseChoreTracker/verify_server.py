import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ssh_config import HOST, PASSWORD, SU, USER  # noqa: E402

import time

import paramiko


def run(ssh, cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
    stdout.channel.settimeout(60)
    out = stdout.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return code, out


ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)
time.sleep(15)

for label, cmd in [
    ("containers", SU + '\'docker ps --format "{{.Names}} | {{.Status}}"\''),
    ("signal", "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/v1/about"),
    ("chore", "curl -s http://127.0.0.1:5000/health"),
]:
    code, out = run(ssh, cmd)
    print(f"=== {label} (exit {code}) ===")
    print(out.encode("ascii", errors="replace").decode("ascii"))

ssh.close()
