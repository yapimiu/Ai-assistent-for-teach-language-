#!/usr/bin/env bash
# One-time server preparation for a fresh Ubuntu/Debian VPS.
# Installs Docker + compose plugin, creates ~/romana/backups and a systemd unit
# that starts the compose stack on boot.
# Usage: sudo ./deploy/init-server.sh   (or run as root)
# Prerequisite: the repository is cloned (the unit points at its deploy/ dir).
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Not root; re-running with sudo..."
  exec sudo bash "$0" "$@"
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/deploy/docker-compose.prod.yml"
SERVICE_NAME="romana-compose"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "==> Checking Docker"
if ! command -v docker >/dev/null 2>&1; then
  echo "Installing Docker (official convenience script)..."
  apt-get update
  apt-get install -y --no-install-recommends ca-certificates curl
  curl -fsSL https://get.docker.com | sh
else
  echo "Docker already installed: $(docker --version)"
fi

systemctl enable --now docker

echo "==> Checking Docker Compose plugin"
if ! docker compose version >/dev/null 2>&1; then
  echo "Installing docker-compose-plugin via apt..."
  apt-get update
  apt-get install -y docker-compose-plugin || {
    echo "apt install failed, trying manual download..."
    mkdir -p /usr/libexec/docker/cli-plugins/
    ARCH=$(uname -m)
    if [ "$ARCH" = "x86_64" ]; then ARCH="x86_64"; fi
    curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${ARCH}" \
      -o /usr/libexec/docker/cli-plugins/docker-compose
    chmod +x /usr/libexec/docker/cli-plugins/docker-compose
  }
fi

echo "Docker Compose: $(docker compose version)"

echo "==> Creating directories"
HOME_DIR="${SUDO_USER:+/home/$SUDO_USER}"
HOME_DIR="${HOME_DIR:-$HOME}"
mkdir -p "$HOME_DIR/romana/backups"
echo "Backups dir: $HOME_DIR/romana/backups"

echo "==> Writing systemd unit ${SERVICE_FILE}"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Romana B1 tutor (docker compose production stack)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${REPO_ROOT}
ExecStart=/usr/bin/docker compose -f ${COMPOSE_FILE} up -d
ExecStop=/usr/bin/docker compose -f ${COMPOSE_FILE} stop
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

echo "==> Enabling ${SERVICE_NAME}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"

# The stack needs .env (secrets are never created by this script).
if [ -f "$REPO_ROOT/.env" ]; then
  echo "==> Starting ${SERVICE_NAME}"
  systemctl start "${SERVICE_NAME}.service"
  systemctl --no-pager status "${SERVICE_NAME}.service" || true
else
  echo "WARNING: $REPO_ROOT/.env not found. Service enabled but NOT started."
  echo "Create .env first (see deploy/deploy.md, 'Secrets setup'), then: systemctl start ${SERVICE_NAME}"
fi

echo "Server init finished."
echo "Next: create .env (see deploy/deploy.md), then run ./deploy/deploy.sh for updates."
