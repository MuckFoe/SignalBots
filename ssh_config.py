"""Connection settings for the remote-management scripts.

Every value is read from the environment, falling back to a `.env` file next to
this module. Nothing sensitive is hardcoded here, so this file is safe to
commit. Copy `.env.example` to `.env` and fill it in before running any of the
deploy or check scripts.
"""

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_ENV_FILE = _ROOT / ".env"


def _load_env_file(path: Path) -> None:
    """Populate os.environ from a .env file.

    Deliberately dependency-free: these scripts run on the operator's machine,
    not in a container, so they cannot assume python-dotenv is installed.
    Existing environment variables win over the file.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_env_file(_ENV_FILE)


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(
            f"{name} is not set.\n"
            f"Copy .env.example to .env and fill it in, or export {name} "
            f"before running this script."
        )
    return value


HOST = _require("SSH_HOST")
USER = _require("SSH_USER")
PASSWORD = _require("SSH_PASSWORD")

# Falls back to the login password, which is how the stack is set up today.
ROOT_PASSWORD = os.environ.get("SSH_ROOT_PASSWORD", "").strip() or PASSWORD

REMOTE_ROOT = os.environ.get("REMOTE_ROOT", "/home/signalbot/ProjectHub")

# Sender identity used by the smoke-test payloads in check_bots.py.
TEST_SENDER = os.environ.get("TEST_SENDER", "+10000000000")

# Prefix for commands that must run as root on the remote host.
#
# Concatenate this with the command string rather than interpolating into an
# f-string: the wrapped commands contain Docker --format templates such as
# {{.Names}}, and f-string parsing would collapse those braces.
SU = f"echo {ROOT_PASSWORD} | su root -c "
