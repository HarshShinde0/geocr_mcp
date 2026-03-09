# GeoCroissant MCP Server

GeoCroissant MCP Server is a Model Context Protocol (MCP) server that provides a Geo-ML Assistant. It enables AI agents and frontend applications to discover, format, and interact with EO data and ML-ready datasets dynamically.

## Getting Started

You can run the MCP server in two ways:
1. **Local Mode**: Ideal for testing tools instantly in VS Code, Claude Desktop, or Antigravity IDE without HTTP latency.
2. **Remote Mode**: Ideal for connecting a production Frontend application, or using your agent from any machine via HTTP Server-Sent Events (SSE).

## 1. Local Development

For the best developer experience in your IDE, connect locally using Python. This method doesn't require open network ports and executes directly on your machine.

### Prerequisites
- Python 3.10+
- The required Python packages installed via `pip install -r requirements.txt`

### Setup for VS Code / Claude Desktop / Antigravity IDE
Add the following to your `mcp_config.json` (or Claude desktop config) file:

```json
{
    "mcpServers": {
        "geocr": {
            "command": "python",
            "args": [
                "-m",
                "src.cli"
            ],
            "env": {
                "PYTHONPATH": "/absolute/path/to/your/geocr_mcp/folder"
            }
        }
    }
}
```
*Note: Make sure to replace `/absolute/path/to/your/geocr_mcp/folder` with the actual path to this repository on your computer.*

## 2. Remote Deployment

This repository is already configured to be instantly deployed to Render as a Web Service.

## Connecting to your Remote Server

Once your server is hosted on Render, you can connect to it in two ways:

### A. From an AI Agent / IDE (VS Code, Claude Desktop)
If you want your IDE to use the remote HTTP server instead of a local Python process, you use `mcp-remote` as a bridge proxy. 

Update your `mcp_config.json`:
```json
{
    "mcpServers": {
        "geocr": {
            "command": "npx",
            "args": [
                "-y",
                "mcp-remote",
                "https://geocr-mcp.onrender.com/sse"
            ]
        }
    }
}
```

### B. From a Web Application
If you are building a React, Next.js, or Svelte application that needs to talk to this MCP, you must connect over HTTP/SSE.

1. Install the MCP SDK in your frontend project:
   ```bash
   npm install @modelcontextprotocol/sdk
   ```

2. Connect via Javascript/Typescript:
   ```javascript
   import { Client } from "@modelcontextprotocol/sdk/client/index.js";
   import { SSEClientTransport } from "@modelcontextprotocol/sdk/client/sse.js";
   
   async function start() {
     const transport = new SSEClientTransport(
       new URL("https://geocr-mcp.onrender.com/sse")
     );
     
     const client = new Client(
       { name: "my-frontend", version: "1.0.0" },
       { capabilities: { tools: {} } }
     );
     
     await client.connect(transport);
     console.log("Connected to GeoCR MCP remotely over SSE!");
     
     const tools = await client.listTools();
     console.log(tools);
   }
   ```
