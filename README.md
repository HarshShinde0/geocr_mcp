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

### Claude Desktop and Claude Code

```json
{
  "mcpServers": {
    "geocr": {
      "command": "uvx",
      "args": [
        "--from",
        "geocr-mcp @ git+https://github.com/HarshShinde0/geocr_mcp.git@main",
        "geocr-mcp-server"
      ],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    }
  }
}
```

### VS Code and Cursor

```json
{
  "mcp": {
    "servers": {
      "geocr": {
        "command": "uvx",
        "args": [
          "--from",
          "geocr-mcp @ git+https://github.com/HarshShinde0/geocr_mcp.git@main",
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

### Local development checkout

Use the project directory when testing changes to the server itself:

```json
{
  "mcpServers": {
    "geocr": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/geocr_mcp",
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

Connect an MCP client to it with:

```json
{
  "mcpServers": {
    "geocr-remote": {
      "url": "https://geocr-mcp-server.onrender.com/mcp"
    }
  }
}
```

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
