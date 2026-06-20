#!/usr/bin/env bash

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

node_version_ok() {
  have_cmd node || return 1
  local major
  major="$(node -p 'process.versions.node.split(".")[0]')"
  [[ "${major:-0}" -ge 18 ]]
}

python_has_venv() {
  python3 -c "import venv" >/dev/null 2>&1
}

python_version_ok() {
  local version major minor
  version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  major="${version%%.*}"
  minor="${version##*.}"
  [[ -n "${version:-}" ]] || return 1
  [[ "${major:-0}" -eq 3 && "${minor:-0}" -le 12 ]]
}

ensure_linux_packages() {
  if ! have_cmd apt-get; then
    return 1
  fi

  sudo apt-get update
  sudo apt-get install -y python3 python3-venv python3-pip nodejs npm
}

ensure_python_tools() {
  if ! have_cmd python3; then
    echo "python3 is required."
    exit 1
  fi

  if ! have_cmd npm || ! python_has_venv; then
    echo "Installing Linux build prerequisites..."
    ensure_linux_packages
  fi

  if ! python_has_venv; then
    echo "Python is missing the venv module."
    echo "Install python3-venv and try again."
    exit 1
  fi

  if ! python_version_ok; then
    echo "Python 3.12 or earlier is required to build ACELink."
    echo "Use Python 3.12 on Windows, or a Linux Python installation no newer than 3.12."
    exit 1
  fi

  if ! node_version_ok; then
    echo "Node.js 18 or newer is required to build the web UI."
    echo "On Raspberry Pi OS, use a recent release such as Bookworm or newer."
    exit 1
  fi
}

ensure_venv() {
  local venv_dir="$1"
  if [[ ! -x "$venv_dir/bin/python" ]]; then
    if ! python3 -m venv "$venv_dir" >/dev/null 2>&1; then
      echo "Unable to create a Python virtual environment."
      echo "Install python3-venv and try again."
      exit 1
    fi
  fi

  local venv_version venv_major venv_minor
  venv_version="$("$venv_dir/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  venv_major="${venv_version%%.*}"
  venv_minor="${venv_version##*.}"
  if [[ -z "${venv_version:-}" || "${venv_major:-0}" -ne 3 || "${venv_minor:-99}" -gt 12 ]]; then
    echo "The existing .venv was created with Python ${venv_version:-unknown}, but ACELink requires Python 3.12 or earlier on Linux."
    echo "Delete .venv and rerun the script with a supported Python version."
    exit 1
  fi
}

install_python_deps() {
  local venv_py="$1"
  local root_dir="$2"

  "$venv_py" -m pip install --disable-pip-version-check --upgrade pip >/dev/null
  "$venv_py" -m pip install --disable-pip-version-check -r "$root_dir/requirements.txt" >/dev/null
}

build_webui() {
  local root_dir="$1"
  pushd "$root_dir/webui" >/dev/null
  npm ci
  npm run build
  popd >/dev/null
}

ensure_webui_built() {
  local root_dir="$1"
  if [[ ! -f "$root_dir/webui/dist/index.html" ]]; then
    build_webui "$root_dir"
  fi
}

read_config_port() {
  local root_dir="$1"
  local config_file="$root_dir/acelink.config.json"
  local port="8765"

  if [[ -f "$config_file" ]]; then
    port="$(python3 -c 'import json, pathlib, sys; path = pathlib.Path(sys.argv[1]); data = json.loads(path.read_text(encoding="utf-8")); print(data.get("port", 8765))' "$config_file" 2>/dev/null || echo 8765)"
  fi

  echo "${port:-8765}"
}
