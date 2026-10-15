#!/usr/bin/env bash
set -euo pipefail

engine="${CONTAINER_ENGINE:-docker}"
container="sommerauer-image-smoke-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"
volume="${container}-data"
trap '"$engine" rm -f "$container" >/dev/null 2>&1 || true; "$engine" volume rm "$volume" >/dev/null 2>&1 || true' EXIT

"$engine" volume create "$volume"
"$engine" run -d --name "$container" --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --volume "$volume:/data" --cap-drop ALL --security-opt no-new-privileges \
  -p 127.0.0.1:18000:8000 -e MODBUS_HOST= -e COLLECTOR_ENABLED=false \
  "$IMAGE:$APP_VERSION"

curl --fail --silent --show-error --retry 12 --retry-delay 1 --retry-all-errors \
  http://127.0.0.1:18000/api/health \
  | python -c 'import json,sys; assert json.load(sys.stdin) == {"status": "ok", "database": "ok"}'
curl --fail --silent --show-error http://127.0.0.1:18000/api/version \
  | python -c 'import json,os,sys; assert json.load(sys.stdin) == {"version": os.environ["APP_VERSION"], "revision": os.environ["GITHUB_SHA"]}'
curl --fail --silent --show-error http://127.0.0.1:18000/api/collector/status \
  | python -c 'import json,sys; assert json.load(sys.stdin)["state"] == "unconfigured"'
