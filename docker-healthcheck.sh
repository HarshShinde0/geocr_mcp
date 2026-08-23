#!/bin/sh
# Healthcheck for the geocr-mcp-server container.
# The MCP protocol has no liveness endpoint, so verify the server process
# (installed entry point) is alive. Match on the entry-point path only, not the
# full command line: the server may carry CLI arguments such as
# `--transport streamable-http --host 0.0.0.0 --port 8000`.

# Check HTTP status endpoint if running in hosted mode (port set or listening)
PORT_TO_CHECK="${PORT:-8000}"
if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT_TO_CHECK}/')" 2>/dev/null; then
  echo "geocr-mcp-server HTTP healthcheck OK";
  exit 0;
fi;

# Fallback: check process entrypoint
if pgrep -f "geocr-mcp-server" > /dev/null; then
  echo "geocr-mcp-server process is running";
  exit 0;
fi;

# Unhealthy
exit 1;

