# GeoCroissant MCP Server

Model Context Protocol (MCP) server for [GeoCroissant](http://mlcommons.org/croissant/geo/1.0) and its geospatial extension.

## Features

- **EO dataset discovery** - keyword/topic search over STAC collections and
  spatial scene search (bbox + datetime + cloud cover) against the live
  **Element84 Earth Search API** (`https://earth-search.aws.element84.com/v1`,
  AWS Open Data), with sensor-modality classification
  (optical / radar / elevation) and theme shortcuts (`flood`, `wildfire`,
  `ndvi`, `dem`, ...).
- **STAC -> GeoCroissant generation** - turns live search results into a
  validated GeoCroissant document: schema.org coverage, CRS, band
  configuration & spectral metadata derived from `eo:bands` (converted from
  micrometers to nanometers), distribution FileObjects for direct asset URLs,
  and a RecordSet embedding one row per scene.
- **Official validator as a tool** - structured pass/fail reports with errors
  and warnings from `mlcroissant` (the same engine as `mlcroissant validate`).
- **Deep inspection** - core metadata plus every GeoCroissant property: CRS,
  spatial/temporal resolution, band configuration, spectral band metadata,
  record endpoint, spatial index/bias/sampling strategy.
- **Structure graph extraction** - exposes the directed multigraph the library
  builds internally (Metadata / FileObject / FileSet / RecordSet / Field nodes;
  source, join and containment edges).
- **Record materialization** - executes the real operation graph (downloads,
  extracts, transforms) to preview actual records, exactly like
  `Dataset.records(...)` in Python.
- **Validated scaffolding** - generates standards-conformant GeoCroissant
  JSON-LD from structured parameters and checks it through the real validator.
- **Built-in spec reference** - namespaces, all `geocr:` properties with
  domains/cardinality, canonical `@context`, sample document and Python API.

## Tools

| Tool | Description |
|------|-------------|
| `list_eo_catalogs` | Registered EO STAC catalogs (Earth Search) with modalities, curated collections and topic keywords. |
| `search_eo_datasets` | Topic/keyword search over Earth Search collections - `'flood'` -> Sentinel-1 + Sentinel-2, `'dem'` -> Copernicus DEM, etc. |
| `search_eo_scenes` | Spatial/temporal/cloud-cover scene search in a bbox; returns per-scene ids, dates, cloud cover, native EPSG and asset keys. |
| `create_geocroissant_from_stac` | End-to-end pipeline: live STAC search -> validated GeoCroissant JSON-LD (coverage, CRS, bands & spectral metadata, distribution URLs, inline scene records). Optionally writes to disk. |
| `validate_croissant` | Validate a Croissant/GeoCroissant document (file path, URL or inline JSON). Returns `valid`, `errors`, `warnings`, conformance targets. |
| `inspect_geocroissant` | Structured summary of a document: metadata, `geocr:` properties, distribution entries and every RecordSet/Field with types, shapes and source chains. |
| `get_structure_graph` | Nodes and directed edges of the library's internal structure graph - lineage and dependency analysis. |
| `list_record_sets` | RecordSets with @ids, keys, inline record/example counts and nested field summaries. |
| `get_records_preview` | Materialize the first N records of a RecordSet, optionally filtered. Executes downloads/transforms like the Python API. |
| `extract_distribution_urls` | Downloadable URLs from the distribution: `contentUrl`, formats, md5/sha256, FileSet includes. |
| `create_geocroissant_scaffold` | Generate a validated GeoCroissant document from parameters (no network needed). Optionally writes to disk. |
| `get_geocroissant_spec_reference` | Specification reference: `overview`, `context`, `properties`, `example`, `python-api` or `all`. |

## Adding a catalog

The registry is **data-driven** (`src/geocr_mcp_server/config/catalogs.yaml`):
each catalog is an entry with its STAC URL, curated collections per modality,
plus shared `topics` and modality keyword hints. To register another catalog
without touching code:

1. Copy the YAML somewhere and append your catalog under `catalogs`
   (and any theme mappings under `topics`).
2. Point the environment variable at it:

```json
"env": { "GEOCR_CATALOGS_CONFIG": "/path/to/catalogs.yaml" }
```

The loader validates that topic references exist in some catalog's collection
lists, so typos fail fast at startup.

## Recommended agent workflow

```
discovery:  list_eo_catalogs -> search_eo_datasets("burn scar", modality=optical)
            -> search_eo_scenes(bbox=[...], datetime_range=...)
metadata:   create_geocroissant_from_stac(...)  # validated output + optional file
consuming:  inspect_geocroissant -> get_records_preview -> extract_distribution_urls
authoring:  create_geocroissant_scaffold -> edit -> validate_croissant
```

## Installation

No clone needed - pip/uvx fetch both `geocr-mcp` and its `mlcroissant` dependency straight from GitHub. Cloning is only required for development.

### pip

```bash
pip install git+https://github.com/HarshShinde0/geocr_mcp.git@main
```

The single dependency `mlcroissant` is pulled automatically from the GeoCroissant fork:

```bash
pip install git+https://github.com/HarshShinde0/croissant.git@main#subdirectory=python/mlcroissant
```

### uv / uvx (recommended for clients)

```bash
uvx --from "geocr-mcp @ git+https://github.com/HarshShinde0/geocr_mcp.git@main" geocr-mcp-server
```

### Docker

```bash
docker build -t geocr-mcp-server .
# stdio (local clients):
docker run -i --rm geocr-mcp-server
# hosted (HTTP transports):
docker run -p 8000:8000 geocr-mcp-server --transport streamable-http --host 0.0.0.0 --port 8000
```

## Client configuration

No clone needed - clients install (and cache) both packages directly from GitHub via `uvx`.

<details>
<summary>Claude Desktop / Claude Code</summary>

```json
{
  "mcpServers": {
    "geocr": {
      "command": "uvx",
      "args": [
        "--from", "geocr-mcp @ git+https://github.com/HarshShinde0/geocr_mcp.git@main",
        "geocr-mcp-server"
      ],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```
</details>

<details>
<summary>VS Code / Cursor</summary>

```json
{
  "mcp": {
    "servers": {
      "geocr": {
        "command": "uvx",
        "args": [
          "--from", "geocr-mcp @ git+https://github.com/HarshShinde0/geocr_mcp.git@main",
          "geocr-mcp-server"
        ],
        "env": {
          "FASTMCP_LOG_LEVEL": "ERROR"
        }
      }
    }
  }
}
```
</details>

<details>
<summary>Running from a local clone (development)</summary>

Only needed when iterating on the server code itself:

```bash
git clone https://github.com/HarshShinde0/geocr_mcp.git   # or this monorepo
```

```json
{
  "mcpServers": {
    "geocr": {
      "command": "uv",
      "args": [
        "--directory", "/path/to/geocr_mcp",
        "run", "geocr-mcp-server"
      ],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```
</details>

<details>
<summary>Hosted deployment (Render / Cloud / HTTP / SSE)</summary>

Run the same server with an HTTP transport for shared/remote cloud usage:

```bash
geocr-mcp-server --transport streamable-http --host 0.0.0.0 --port $PORT
```

#### Deploy on Render (1-Click Blueprint)

This repository includes a `render.yaml` blueprint:

1. Log in to [Render Dashboard](https://dashboard.render.com).
2. Click **New +** -> **Blueprint** and connect repository `HarshShinde0/geocr_mcp`.
3. Click **Apply**. Render will automatically build the container and deploy the server.

Live endpoint: `https://geocr-mcp-server.onrender.com/mcp`

#### Connecting Clients to Hosted MCP

In your AI client, IDE, or agent configuration (`mcpServers`):

```json
{
  "mcpServers": {
    "geocr-remote": {
      "url": "https://geocr-mcp-server.onrender.com/mcp"
    }
  }
}
```

Behind a custom reverse proxy, terminate TLS at the proxy and set `GEOCR_HOST=0.0.0.0` and `GEOCR_TRANSPORT=streamable-http`.
</details>

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FASTMCP_LOG_LEVEL` | `WARNING` | Log level for stderr logging (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `GEOCR_OUTPUT_DIR` | system temp dir | Directory where generated files are written (filenames are sanitized to basenames). |
| `GEOCR_CATALOGS_CONFIG` | shipped YAML | Path to an alternate catalog registry file - add catalogs/topics without code changes. |
| `GEOCR_HOST` / `GEOCR_PORT` | `127.0.0.1` / `8000` | Bind address for SSE/streamable-http transports (also settable via CLI flags). |

## Security considerations

- The server performs **network requests only when a tool input references a URL**
  or when materializing records from remote distributions (`get_records_preview`).
  Keep `limit` small in untrusted contexts.
- Generated files are always written inside `GEOCR_OUTPUT_DIR`; path traversal is
  blocked by reducing filenames to their basename.
- Run containers as non-root (the provided Dockerfile already does).

## Development

```bash
cd geocr_mcp
uv venv && uv sync --all-groups     # or: python -m pip install -e ".[dev]"
uv run pytest --cov --cov-branch    # unit tests (no network required)
uv run ruff check src tests         # lint (same rules as awslabs/mcp)
npx @modelcontextprotocol/inspector geocr-mcp-server   # interactive debugging
```
