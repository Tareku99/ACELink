#!/usr/bin/env bash
set -euo pipefail

container=$(docker run --detach --publish 127.0.0.1::8765 "$1" --debug)
cleanup() {
  result=$?
  if (( result != 0 )); then
    docker logs "$container" >&2 || true
  fi
  docker rm --force --volumes "$container" >/dev/null || true
}
trap cleanup EXIT

address=$(docker port "$container" 8765/tcp)
for ((attempt = 0; attempt < 30; attempt++)); do
  if curl --fail --silent --max-time 2 "http://$address/" >/dev/null &&
     curl --fail --silent --max-time 2 "http://$address/devices" >/dev/null &&
     docker exec "$container" test -s /data/acelink.config.json; then
    exit 0
  fi
  sleep 1
done
exit 1
