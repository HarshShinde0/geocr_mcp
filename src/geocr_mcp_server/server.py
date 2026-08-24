"""GeoCroissant MCP server implementation.

Exposes Earth observation discovery and Croissant and GeoCroissant metadata
operations to MCP clients.
"""

import argparse
import os
import sys
from geocr_mcp_server import __version__
from geocr_mcp_server.tools import GeoCroissantTools
from loguru import logger
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings


logger.remove()
logger.add(sys.stderr, level=os.getenv('FASTMCP_LOG_LEVEL', 'WARNING'))

is_cloud = bool(os.getenv('PORT') or os.getenv('RENDER'))
transport_sec = (
    TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
        allowed_hosts=['*'],
        allowed_origins=['*'],
    )
    if is_cloud
    else None
)

mcp = FastMCP(
    'geocr-mcp-server',
    transport_security=transport_sec,
    instructions=f"""
# Croissant / GeoCroissant MCP Server (v{__version__})

Discover **Earth observation (EO) datasets** and turn them into
**GeoCroissant**, the geospatial extension of the MLCommons Croissant JSON-LD
dataset format. Discovery queries registered STAC APIs. The configured
`mlcroissant` package handles metadata parsing, validation, structure graphs,
and record materialization.

## Capabilities
- **EO discovery**: paginated collection inventories, provider metadata,
    place-name geocoding, availability counts and spatial scene search.
- **STAC -> GeoCroissant**: generate metadata from search results, including
    coverage, CRS, band metadata, selected source URIs, and one record per scene.
- **Multi-source composition**: combine independent searches from any
    registered catalogs into source-specific RecordSets without assuming
    spatial, temporal, spectral, or tensor alignment.
- Validate any Croissant/GeoCroissant document (file, URL or inline JSON)
  with structured error/warning reports.
- Inspect datasets: core metadata plus every `geocr:` property.
- Extract the internal structure graph (nodes + directed edges).
- List RecordSets, materialize records, and inspect distribution URIs.
- Generate scaffolds from structured parameters.
- Serve the GeoCroissant specification reference.

## Natural-language request workflow
The client LLM interprets the user's question; this server does not use
hard-coded topic, keyword or modality routing.
1. Extract the requested phenomenon/product, place, dates and constraints.
    Ask the user only when a required choice is genuinely ambiguous.
2. Resolve place names with `geocode_place` and let the user disambiguate
    when multiple plausible candidates are returned.
3. Call `list_eo_catalogs`, page through `search_eo_datasets`, and inspect
    plausible candidates with `get_eo_dataset_details`. Select collections
    from their live metadata, never from collection-id wording alone.
4. Call `count_eo_scenes` to verify availability, then `search_eo_scenes`.
5. Call `create_geocroissant_from_stac` for one search or
    `create_geocroissant_from_stac_sources` for multiple independent sources.
    Return its `json_ld`, validation report, and selected `asset_urls`. The
    provider retains the data and may require credentials or a
    provider-specific access method.
6. Use `get_records_preview` for inline scene rows and
    `extract_distribution_urls` to inspect an existing document.

## Best practices
- Bounding boxes use [min_lon, min_lat, max_lon, max_lat] (EPSG:4326).
- Keep `limit` modest: searches hit live STAC APIs; generation embeds scenes
  as inline records.
- Use `max_cloud_cover` only when the chosen collection metadata supports
    `eo:cloud_cover`.
- Multi-source metadata preserves provenance but does not align or preprocess
    the source data for a model.
- Always re-run `validate_croissant` after editing any document.
- Metadata validation does not verify that source assets exist or are accessible.
""",
    dependencies=[
        'mlcroissant',
        'mcp',
        'pydantic',
        'loguru',
    ],
)

tools = GeoCroissantTools()
tools.register(mcp)
logger.info('GeoCroissant tools registered successfully')


@mcp.custom_route('/', methods=['GET', 'HEAD'])
async def root_status(request):
    """Health status root endpoint for Render and monitoring tools."""
    from starlette.responses import JSONResponse


    return JSONResponse({
        'status': 'online',
        'server': 'geocr-mcp-server',
        'version': __version__,
        'description': 'GeoCroissant MCP Server is running and healthy.',
        'mcp_endpoint': '/mcp',
        'documentation': 'https://github.com/HarshShinde0/geocr_mcp',
    })


def main():
    """Run the MCP server (stdio by default; SSE/HTTP for hosted setups)."""
    # Cloud environments (Render, Railway, Heroku, Cloud Run) set PORT or RENDER
    is_cloud = bool(os.getenv('PORT') or os.getenv('RENDER'))
    default_transport = os.getenv('GEOCR_TRANSPORT', 'streamable-http' if is_cloud else 'stdio')
    default_host = os.getenv('GEOCR_HOST', '0.0.0.0' if is_cloud else '127.0.0.1')

    parser = argparse.ArgumentParser(
        prog='geocr-mcp-server', description='Croissant / GeoCroissant MCP server'
    )
    parser.add_argument(
        '--transport',
        choices=['stdio', 'sse', 'streamable-http'],
        default=default_transport,
        help='Transport mode (default: stdio locally, streamable-http in cloud)',
    )
    parser.add_argument(
        '--host',
        default=default_host,
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

    if (is_cloud or args.host == '0.0.0.0') and mcp.settings.transport_security:
        mcp.settings.transport_security.allowed_hosts = ['*']
        mcp.settings.transport_security.allowed_origins = ['*']

    logger.info(f'geocr-mcp-server v{__version__} starting ({args.transport})')
    mcp.run(transport=args.transport)


if __name__ == '__main__':
    main()
