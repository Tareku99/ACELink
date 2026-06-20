#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$ROOT_DIR/.venv"

source "$SCRIPT_DIR/common.sh"

ensure_python_tools
ensure_venv "$VENV_DIR"
VENV_PY="$VENV_DIR/bin/python"
install_python_deps "$VENV_PY" "$ROOT_DIR"
build_webui "$ROOT_DIR"

PORT="$(read_config_port "$ROOT_DIR")"
echo
echo "ACELink"
echo "-------"
echo
echo "Web UI:  http://localhost:${PORT}"
echo "Press Ctrl+C to stop"
echo
exec "$VENV_PY" "$ROOT_DIR/main.py"
