"""geocr MCP Server implementation.

Exposes MLCommons Croissant / GeoCroissant capabilities to LLM agents:
validation through the official ``mlcroissant`` library, structured dataset
inspection, structure-graph extraction, record materialization and validated
GeoCroissant metadata scaffolding.
"""

import argparse
import os
import sys
from geocr_mcp_server import __version__
from geocr_mcp_server.tools import GeoCroissantTools
from loguru import logger
from mcp.server.fastmcp import FastMCP


logger.remove()
logger.add(sys.stderr, level=os.getenv('FASTMCP_LOG_LEVEL', 'WARNING'))

mcp = FastMCP(
    'geocr-mcp-server',
    instructions=f"""
# Croissant / GeoCroissant MCP Server (v{__version__})

Discover **Earth observation (EO) datasets** and turn them into
**GeoCroissant** - the geospatial extension of the MLCommons Croissant
machine-actionable JSON-LD dataset format. All parsing, validation and record
extraction are performed by the official `mlcroissant` Python library; all
discovery runs against the live Earth Search STAC API (AWS Open Data,
https://earth-search.aws.element84.com/v1).

## Capabilities
- **EO discovery**: keyword search over EO collections, spatial scene search
  (bbox + datetime + cloud cover) across registered STAC catalogs.
- **STAC -> GeoCroissant**: generate standards-conformant metadata directly
  from live search results (coverage, CRS, bands & spectral metadata,
  distribution URLs, one record per scene) - validated before returned.
- Validate any Croissant/GeoCroissant document (file, URL or inline JSON)
  with structured error/warning reports.
- Inspect datasets: core metadata plus every `geocr:` property.
- Extract the internal structure graph (nodes + directed edges).
- List RecordSets, materialize actual records, extract download URLs.
- Generate validated scaffolds from structured parameters.
- Serve the GeoCroissant specification reference.

## Recommended workflow
1. Discover: `list_eo_catalogs` once, then `search_eo_datasets`
   ("burn scar", "flood", modality=optical...) or straight to
   `search_eo_scenes` with a bbox over the area of interest.
2. Metadata: `create_geocroissant_from_stac` on promising results - it returns
   a VALIDATED GeoCroissant document (and can write it via output_filename).
3. Consume: `inspect_geocroissant`, `get_records_preview` (inline scene rows),
   `extract_distribution_urls` for direct asset links; write training code
   against actual field ids.
4. Authoring from scratch: `create_geocroissant_scaffold` +
   `validate_croissant`.

## Best practices
- Bounding boxes use [min_lon, min_lat, max_lon, max_lat] (EPSG:4326).
- Keep `limit` modest: searches hit live STAC APIs; generation embeds scenes
  as inline records.
- Always re-run `validate_croissant` after editing any document.
""",
    dependencies=[
        'mlcroissant',
        'mcp',
        'pydantic',
        'loguru',
    ],
)

try:
    tools = GeoCroissantTools()
    tools.register(mcp)
    logger.info('GeoCroissant tools registered successfully')
except Exception as e:
    logger.error(f'Error initializing GeoCroissant tools: {e}')
    raise


def main():
    """Run the MCP server (stdio by default; SSE/HTTP for hosted setups)."""
    parser = argparse.ArgumentParser(
        prog='geocr-mcp-server', description='Croissant / GeoCroissant MCP server'
    )
    parser.add_argument(
        '--transport',
        choices=['stdio', 'sse', 'streamable-http'],
        default=os.getenv('GEOCR_TRANSPORT', 'stdio'),
        help='Transport mode (default: stdio or GEOCR_TRANSPORT env)',
    )
    parser.add_argument(
        '--host',
        default=os.getenv('GEOCR_HOST', '127.0.0.1'),
        help='Bind host for sse/streamable-http transports',
    )
    parser.add_argument(
        '--port',
        type=int,
        default=int(os.getenv('GEOCR_PORT', os.getenv('PORT', '8000'))),
        help='Port for sse/streamable-http transports',
    )
    args = parser.parse_args()

    mcp.settings.host = args.host
    mcp.settings.port = args.port

    logger.info(f'geocr-mcp-server v{__version__} starting ({args.transport})')
    mcp.run(transport=args.transport)


if __name__ == '__main__':
    main()
