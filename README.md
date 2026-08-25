# GeoCroissant MCP Server

The GeoCroissant MCP Server gives Model Context Protocol (MCP) clients access
to [GeoCroissant](http://mlcommons.org/croissant/geo/1.0), the geospatial
extension of [MLCommons Croissant](https://mlcommons.org/croissant/).

Through Model Context Protocol (MCP), a client can explore Earth observation
datasets in catalogs and create GeoCroissant ML-Ready Metadata from selected scenes,
validate metadata, inspect dataset structure, and preview records with
`mlcroissant`.

> [!NOTE]
> The server provides current catalog and dataset information. The connected
> MCP client uses this information to understand the request and choose a
> suitable catalog and collection.

## GeoCroissant workflow

A client can create and explore a GeoCroissant dataset in one workflow:

1. List the registered STAC catalogs.
2. Search their current collections and review the most relevant results.
3. Resolve a place to an EPSG:4326 bounding box when coordinates are not
   already available.
4. Count matching scenes before requesting records.
5. Generate GeoCroissant JSON-LD for the chosen collections, area, dates, and
  optional cloud-cover limit.
6. Validate or inspect the resulting metadata and preview its records.

```text
user request
  -> select a catalog from list_eo_catalogs
  -> find collections with search_eo_datasets
  -> inspect candidates with get_eo_dataset_details
  -> resolve a place with geocode_place, when needed
  -> verify availability with count_eo_scenes
  -> generate one source with create_geocroissant_from_stac
     or multiple sources with create_geocroissant_from_stac_sources
  -> use json_ld and asset_urls in the client
```

The result describes the dataset's location, time range, coordinate reference
system, raster bands, and available spectral properties. Each selected STAC
scene becomes an inline record connected to its source assets.

> [!TIP]
> **Remote clients:** Generation returns the complete document in `json_ld`.
> A returned `path` refers to the server's filesystem, so a remote client
> should use `json_ld` when it needs to store the document locally.

## MCP tools

| Tool | Purpose |
|------|---------|
| `ping` | Return `pong` to confirm that the MCP server is available. |
| `create_geocroissant_from_stac` | Create GeoCroissant JSON-LD from a STAC search and return the selected source asset URIs. |
| `create_geocroissant_from_stac_sources` | Compose independent searches from any registered catalogs into source-specific RecordSets. |
| `create_geocroissant_scaffold` | Create a GeoCroissant starting point from dataset details and return its validation result. |
| `validate_croissant` | Check a document and return validation errors, warnings, and conformance information. |
| `inspect_geocroissant` | Summarize the dataset, geospatial properties, distributions, RecordSets, and Fields. |
| `get_structure_graph` | Show the nodes and relationships in the metadata graph. |
| `list_record_sets` | List RecordSets and their keys, records, examples, and Fields. |
| `get_records_preview` | Read a small, optionally filtered sample from a RecordSet. |
| `extract_distribution_urls` | List distribution URIs, media types, checksums, archive links, and FileSet patterns. |
| `get_geocroissant_spec_reference` | Read the GeoCroissant overview, context, properties, example, or Python API reference. |
| `list_eo_catalogs` | List the STAC services in the active YAML configuration. |
| `search_eo_datasets` | Browse collections from a selected STAC service. |
| `get_eo_dataset_details` | Read the provider's details for one collection. |
| `geocode_place` | Find candidate EPSG:4326 bounding boxes for a place name. |
| `count_eo_scenes` | Count scenes for the chosen collections, area, dates, and optional cloud-cover limit. |
| `search_eo_scenes` | Find STAC scenes that match the selected collections and search options. |

## Source assets

The generated metadata keeps each selected asset URI in the format published
by its STAC provider, including `s3://`, `https://`, and other supported URI
schemes. Clients can then access each source using the connection method and
credentials provided for that service.

## Multiple sources

`create_geocroissant_from_stac_sources` accepts an arbitrary list of explicit
STAC searches. Each source requires `catalog_id`, `collection_id`, and an
EPSG:4326 `bbox`; it can also set `source_id`, `datetime_range`,
`max_cloud_cover`, and `limit`. Catalog IDs must exist in the active YAML
registry. Sources may use different catalogs or repeat one catalog with
different collections.

```json
{
  "name": "Combined observations",
  "sources": [
    {
      "source_id": "source_a",
      "catalog_id": "catalog-a",
      "collection_id": "collection-a",
      "bbox": [-53, -31, -50, -28],
      "datetime_range": "2026-08-01/2026-08-25",
      "limit": 10
    },
    {
      "source_id": "source_b",
      "catalog_id": "catalog-b",
      "collection_id": "collection-b",
      "bbox": [-53, -31, -50, -28],
      "limit": 10
    }
  ]
}
```

The result contains one RecordSet per source, source and catalog provenance,
provider-native asset URIs, and per-source search results. It records the
selected observations without claiming that sources are spatially,
temporally, spectrally, or tensor aligned. Downstream code must apply the
dataset-specific access, alignment, and preprocessing required for its model.

## Catalog registry

The bundled registry is
`src/geocr_mcp_server/config/catalogs.yaml`. It currently defines:

- `earth-search`: Element84 Earth Search, the default catalog.
- `veda`: NASA Visualization, Exploration, and Data Analysis (VEDA).

Each entry contains an identifier, display name, STAC endpoint, description,
and a collection snapshot. Searches use the provider's current catalog, so
new collections can appear before the snapshot is updated. When `catalog_id`
is omitted, `default_catalog` selects the service.

To use another registry, copy the YAML file, add the required catalog entries,
and set its absolute path in the server environment:

```json
{
  "env": {
    "GEOCR_CATALOGS_CONFIG": "/path/to/catalogs.yaml"
  }
}
```

No Python change is required. The server checks the configuration when it
loads the registry.

## Installation

Python 3.10 or newer is required. For an MCP client, `uvx` can install and run
the server without a manual checkout:

```bash
uvx --from "geocr-mcp @ git+https://github.com/HarshShinde0/geocr_mcp.git@main" geocr-mcp-server
```

To install the command in the active Python environment:

```bash
pip install git+https://github.com/HarshShinde0/geocr_mcp.git@main
```

The installation includes the GeoCroissant-enabled `mlcroissant` dependency.

### Docker

```bash
docker build -t geocr-mcp-server .
docker run -i --rm geocr-mcp-server
```

For streamable HTTP:

```bash
docker run -p 8000:8000 geocr-mcp-server \
  --transport streamable-http --host 0.0.0.0 --port 8000
```

## Client configuration

The clients below use different configuration filenames and remote-server keys.
Use the example for your client rather than copying a configuration between
clients unchanged.

Configuration references: [VS Code](https://code.visualstudio.com/docs/copilot/chat/mcp-servers),
[Cursor](https://cursor.com/docs/context/mcp),
[Antigravity](https://antigravity.google/docs/mcp),
[Kiro](https://kiro.dev/docs/mcp/configuration/), [Claude Code](https://code.claude.com/docs/en/mcp), and
[OpenCode](https://opencode.ai/docs/mcp-servers/). Claude Desktop configures
[remote custom connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)
through the Claude account.

### VS Code

> [!TIP]
> Use `.vscode/mcp.json` with the top-level `servers` key. Hosted servers use
> `type: "http"`; local servers use `type: "stdio"` with `command` and `args`.

#### Hosted server

Add the hosted streamable HTTP server to `.vscode/mcp.json`:

```json
{
  "servers": {
    "geocr-mcp": {
      "type": "http",
      "url": "https://geocr-mcp-server.onrender.com/mcp"
    }
  },
  "inputs": []
}
```

#### Local development checkout

Use the local project directory and stdio transport when testing server changes.
For this repository checkout, add the following to `.vscode/mcp.json`:

```json
{
  "servers": {
    "geocr-mcp-local": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "--directory",
        "${workspaceFolder}/geocr_mcp",
        "run",
        "geocr-mcp-server"
      ],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    }
  },
  "inputs": []
}
```

When `geocr_mcp` itself is the workspace root, use `${workspaceFolder}` instead.
Do not add the `--transport stdio` arguments: stdio is already the local default.

Run **MCP: List Servers** from the Command Palette to inspect the connection and
server output.

### Cursor

> [!TIP]
> Use `.cursor/mcp.json` with the top-level `mcpServers` key. Hosted servers use
> `url`; local servers use `type: "stdio"` with `command` and `args`.

Add project-specific servers to `.cursor/mcp.json`, or use
`~/.cursor/mcp.json` to make them available in every project.

#### Hosted server

```json
{
  "mcpServers": {
    "geocr-mcp": {
      "url": "https://geocr-mcp-server.onrender.com/mcp"
    }
  }
}
```

#### Local development checkout

```json
{
  "mcpServers": {
    "geocr-mcp-local": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "--directory",
        "${workspaceFolder}/geocr_mcp",
        "run",
        "geocr-mcp-server"
      ],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    }
  }
}
```

When `geocr_mcp` itself is the project root, use `${workspaceFolder}` instead.
Check **Customize > MCP** for server status, or select **MCP Logs** in Cursor's
Output panel.

### Antigravity

> [!TIP]
> Use `.agents/mcp_config.json` with the top-level `mcpServers` key. Hosted
> servers must use `serverUrl`, while local servers use `command` and `args`.

Add project-specific servers to `.agents/mcp_config.json`, or use
`~/.gemini/config/mcp_config.json` to make them available globally.

#### Hosted server

Antigravity requires `serverUrl` for remote servers; `url` and `httpUrl` are not
supported.

```json
{
  "mcpServers": {
    "geocr-mcp": {
      "serverUrl": "https://geocr-mcp-server.onrender.com/mcp"
    }
  }
}
```

#### Local development checkout

Replace `/absolute/path/to/croissant` with the path to this repository checkout.

```json
{
  "mcpServers": {
    "geocr-mcp-local": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/croissant/geocr_mcp",
        "run",
        "geocr-mcp-server"
      ],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    }
  }
}
```

Open **MCP Servers > Manage MCP Servers** in the agent panel to reload the
configuration and inspect connection status.

### Kiro

> [!TIP]
> Use `.kiro/settings/mcp.json` with the top-level `mcpServers` key. Hosted
> servers use `url`; local servers use `command` and `args`.

Add project-specific servers to `.kiro/settings/mcp.json`, or use
`~/.kiro/settings/mcp.json` to make them available globally.

#### Hosted server

```json
{
  "mcpServers": {
    "geocr-mcp": {
      "url": "https://geocr-mcp-server.onrender.com/mcp"
    }
  }
}
```

#### Local development checkout

Replace `/absolute/path/to/croissant` with the path to this repository checkout.

```json
{
  "mcpServers": {
    "geocr-mcp-local": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/croissant/geocr_mcp",
        "run",
        "geocr-mcp-server"
      ],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    }
  }
}
```

Kiro reloads the file when it is saved. Check the MCP servers tab in the Kiro
panel; connection logs are available under **Kiro - MCP Logs** in Output.

### Claude Code

> [!TIP]
> Use `.mcp.json` with the top-level `mcpServers` key. Hosted servers require
> `type: "http"` and `url`; local servers use `type: "stdio"`.

Add project-specific servers to `.mcp.json` in the project root.

#### Hosted server

```json
{
  "mcpServers": {
    "geocr-mcp": {
      "type": "http",
      "url": "https://geocr-mcp-server.onrender.com/mcp"
    }
  }
}
```

The equivalent project-scoped command is:

```bash
claude mcp add --transport http --scope project \
  geocr-mcp https://geocr-mcp-server.onrender.com/mcp
```

#### Local development checkout

```json
{
  "mcpServers": {
    "geocr-mcp-local": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "--directory",
        "${CLAUDE_PROJECT_DIR:-.}/geocr_mcp",
        "run",
        "geocr-mcp-server"
      ],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    }
  }
}
```

When `geocr_mcp` itself is the project root, use
`${CLAUDE_PROJECT_DIR:-.}` instead. Run `claude mcp get geocr-mcp` or use `/mcp`
inside Claude Code to verify the connection. Project-scoped servers require
approval when first loaded interactively.

### Claude Desktop

> [!TIP]
> Add hosted servers through **Customize > Connectors**. Use
> `claude_desktop_config.json` only for local stdio servers.

For the hosted server, add the endpoint as a custom connector under
**Customize > Connectors** in Claude; remote connectors are configured through
the Claude account rather than `claude_desktop_config.json`:

```text
https://geocr-mcp-server.onrender.com/mcp
```

For a local server, add a stdio entry to `claude_desktop_config.json`. Replace
`/absolute/path/to/croissant` with the path to this repository checkout:

```json
{
  "mcpServers": {
    "geocr-mcp-local": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/croissant/geocr_mcp",
        "run",
        "geocr-mcp-server"
      ],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    }
  }
}
```

### OpenCode

> [!TIP]
> Use `opencode.json` in the project root (or `~/.config/opencode/opencode.json`
> for global scope) with the top-level `mcp` key — not `mcpServers`. Hosted
> servers require `type: "remote"` and `url`; local servers use
> `type: "local"` with a `command` array and `environment`.

#### Hosted server

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "geocr-mcp": {
      "type": "remote",
      "url": "https://geocr-mcp-server.onrender.com/mcp",
      "timeout": 60000
    }
  }
}
```

The `timeout` is optional but recommended for the hosted server: free-tier
hosting can cold-start for tens of seconds, exceeding OpenCode's default
5-second timeout.

#### Local development checkout

Replace `/absolute/path/to/croissant` with the path to this repository checkout.

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "geocr-mcp-local": {
      "type": "local",
      "command": [
        "uv",
        "--directory",
        "/absolute/path/to/croissant/geocr_mcp",
        "run",
        "geocr-mcp-server"
      ],
      "environment": {
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    }
  }
}
```

When `geocr_mcp` itself is the project root, point `--directory` at `.`.
Config is loaded once at startup, so quit and restart OpenCode after saving;
verify with `opencode mcp list` or by using a tool in a prompt.

## Hosted server

Start a shared endpoint with the streamable HTTP transport:

```bash
geocr-mcp-server \
  --transport streamable-http \
  --host 0.0.0.0 \
  --port "$PORT"
```

The included `render.yaml` deploys the same command on Render. The current
hosted endpoint is:

```text
https://geocr-mcp-server.onrender.com/mcp
```

Use the client-specific hosted configuration above; remote-server keys are not
portable between all clients.

> [!NOTE]
> When a reverse proxy provides TLS, bind the server with
> `GEOCR_HOST=0.0.0.0` and set `GEOCR_TRANSPORT=streamable-http`.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `FASTMCP_LOG_LEVEL` | `WARNING` | Set stderr logging to `DEBUG`, `INFO`, `WARNING`, or `ERROR`. |
| `GEOCR_OUTPUT_DIR` | System temporary directory | Choose where generated files are written. Supplied filenames are reduced to their basename. |
| `GEOCR_CATALOGS_CONFIG` | Bundled YAML registry | Load catalog definitions from another YAML file. |
| `GEOCR_HOST` | `127.0.0.1` locally; `0.0.0.0` in cloud environments | Set the bind address for SSE or streamable HTTP. |
| `GEOCR_PORT` | `8000` | Set the port for SSE or streamable HTTP. |
| `GEOCR_TRANSPORT` | `stdio` locally; `streamable-http` in cloud environments | Select the MCP transport. |

## Network and file handling

- Catalog searches, scene requests, geocoding, URL inputs, and remote record
  previews connect to their configured services.
- Scene and preview limits help keep requests manageable for large datasets.
- Generated files are written inside `GEOCR_OUTPUT_DIR`, and output names are
  reduced to their basename.
- The provided container runs as a non-root user by default.

## Development

From the `geocr_mcp` directory:

```bash
uv venv
uv sync --all-groups
uv run ruff check src tests
uv run python -m pytest --cov --cov-branch
uv run python -m pytest -o addopts='' -m live
```

The default test run covers local behavior and the MCP protocol. The live test
group connects to Earth Search, NASA VEDA, and Nominatim.

For interactive protocol inspection:

```bash
npx @modelcontextprotocol/inspector geocr-mcp-server
```
