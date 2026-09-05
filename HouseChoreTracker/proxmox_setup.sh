#!/usr/bin/env bash
set -euo pipefail

# Proxmox guest bootstrap for Docker + Compose deployment.
# Target: Debian 12 (bookworm) VM or privileged LXC container.

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash proxmox_setup.sh"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
source /etc/os-release

if [[ "${ID:-}" != "debian" || "${VERSION_CODENAME:-}" != "bookworm" ]]; then
  echo "Warning: this script is tuned for Debian 12 (bookworm)."
  echo "Detected: ID=${ID:-unknown}, VERSION_CODENAME=${VERSION_CODENAME:-unknown}"
fi

echo "[1/7] Updating apt packages..."
apt-get update
apt-get upgrade -y

echo "[2/7] Installing dependencies..."
apt-get install -y ca-certificates curl gnupg lsb-release git

echo "[3/7] Adding Docker repository..."
install -m 0755 -d /etc/apt/keyrings
if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
  curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
fi
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list

echo "[4/7] Installing Docker engine and Compose plugin..."
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "[5/7] Enabling Docker service..."
systemctl enable docker
systemctl start docker

echo "[6/7] Docker installed and service started."
echo "[7/7] Done."
echo "Next:"
echo "  1) clone/copy your bot project here"
echo "  2) cp .env.example .env"
echo "  3) set SIGNAL_BOT_NUMBER in .env"
echo "  4) docker compose up -d --build"
