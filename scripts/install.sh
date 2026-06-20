#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$ROOT_DIR/.venv"
INSTALL_USER="${SUDO_USER:-${USER:-$(id -un)}}"

source "$SCRIPT_DIR/common.sh"

echo "Installing or updating ACELink..."

ensure_python_tools
ensure_venv "$VENV_DIR"
VENV_PY="$VENV_DIR/bin/python"
install_python_deps "$VENV_PY" "$ROOT_DIR"
build_webui "$ROOT_DIR"

if have_cmd systemctl; then
  echo "Configuring systemd service..."
  sudo usermod -a -G dialout "$INSTALL_USER" || true

  SERVICE_FILE="/etc/systemd/system/acelink.service"
  sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=ACELink
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$INSTALL_USER
WorkingDirectory=$ROOT_DIR
ExecStart=$VENV_DIR/bin/python "$ROOT_DIR/main.py"
Restart=on-failure
RestartSec=3
SupplementaryGroups=dialout

[Install]
WantedBy=multi-user.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable acelink.service
  sudo systemctl restart acelink.service

  if ! sudo systemctl is-active --quiet acelink.service; then
    echo "ACELink service failed to start."
    sudo systemctl --no-pager -l status acelink.service || true
    exit 1
  fi

  PORT="$(read_config_port "$ROOT_DIR")"
  LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  if [[ -z "${LAN_IP:-}" ]]; then
    LAN_IP="localhost"
  fi

  echo
  echo "ACELink is running."
  echo "Open the web UI at: http://${LAN_IP}:${PORT}"
  echo "Local access also works at: http://localhost:${PORT}"
  echo "If the ACE does not appear yet, reboot once so the dialout group change takes effect."
else
  echo "systemd was not found. Starting ACELink in the foreground."
  PORT="$(read_config_port "$ROOT_DIR")"
  echo "Open the web UI at: http://localhost:${PORT}"
  exec "$VENV_PY" "$ROOT_DIR/main.py"
fi
