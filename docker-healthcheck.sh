#!/bin/sh
# Healthcheck for the geocr-mcp-server container.
# The MCP protocol has no liveness endpoint, so verify the server process
# (installed entry point) is alive. Match on the entry-point path only, not the
# full command line: the server may carry CLI arguments such as
# `--transport streamable-http --host 0.0.0.0 --port 8000`.

if pgrep -f "/app/.venv/bin/geocr-mcp-server" > /dev/null; then
  echo "geocr-mcp-server is running";
  exit 0;
fi;

# Unhealthy
exit 1;
