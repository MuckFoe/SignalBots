import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ssh_config import HOST, PASSWORD, SU, USER  # noqa: E402

import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)
stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8080/v1/accounts")
print(stdout.read().decode("utf-8", errors="replace"))
ssh.close()
