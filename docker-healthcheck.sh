#!/bin/sh
# Healthcheck for the geocr-mcp-server container.
set -eu

PORT_TO_CHECK="${GEOCR_PORT:-${PORT:-8000}}"

check_http() {
  python -c "import json, urllib.request; response = urllib.request.urlopen('http://127.0.0.1:${PORT_TO_CHECK}/', timeout=5); payload = json.load(response); raise SystemExit(0 if payload.get('status') == 'online' else 1)" 2>/dev/null
}

# A hosted service is healthy only when its HTTP endpoint responds correctly.
if [ -n "${PORT:-}" ] || [ "${GEOCR_TRANSPORT:-}" = "streamable-http" ] || [ "${GEOCR_TRANSPORT:-}" = "sse" ]; then
  check_http
  exit $?
fi

# Also support HTTP mode selected with command-line arguments.
if check_http; then
  exit 0
fi

# Stdio has no HTTP endpoint, so its process is the available liveness signal.
pgrep -f "/app/.venv/bin/geocr-mcp-server" >/dev/null

# Unhealthy
exit 1;

