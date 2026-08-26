# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 23-08-2026


First stable release of the GeoCroissant MCP Server. MCP clients can discover
Earth observation data, create GeoCroissant metadata, validate it, and inspect
its records and source files.

> [!NOTE]
> Catalogs are configured only through YAML. The server does not use keywords,
> topics, or data types to choose a catalog or collection.

### Added

- YAML-based STAC catalog configuration with explicit catalog selection.
- Live catalog browsing, collection details, scene counts, and scene search.
- Place-name lookup for finding EPSG:4326 bounding boxes.
- GeoCroissant generation from a single STAC search.
- Multi-source generation across different catalogs or different collections
  in the same catalog.
- A separate RecordSet for each source, with its catalog and source ID kept in
  every record.
- Spatial and time coverage, coordinate systems, raster bands, spectral bands,
  and provider asset details when available.
- Croissant and GeoCroissant validation from a file, URL, or inline JSON-LD.
- Metadata inspection, structure graphs, RecordSet listing, record previews,
  and distribution URI inspection.
- Valid GeoCroissant scaffold generation from structured dataset details.
- A built-in GeoCroissant reference with properties, examples, and Python
  usage.
- Stdio, SSE, and streamable HTTP transports.
- HTTP and MCP health checks, Docker support, and Render deployment settings.
- Responsible AI (Croissant RAI 1.0) and GeoCroissant geographic RAI metadata support.
- Extraction of structured metadata section during inspection.
- MCP tool usage for creating GeoCroissant metadata and AI metadata

> [!TIP]
> Multi-source generation works with any catalogs in the active YAML file. The
> same catalog can also be used more than once.

### Changed

- Dataset selection now uses live provider metadata.
- Cloud-cover filtering is used only when requested.
- Provider asset URIs are kept unchanged, including `https://`, `s3://`, and
  other supported schemes.
- Generated files are written inside `GEOCR_OUTPUT_DIR`. The system temporary
  directory is used by default.

> [!NOTE]
> Multi-source metadata keeps each source separate. It does not align,
> resample, merge, or preprocess source data for a machine learning model.

### Testing

- Added unit, MCP protocol, and live service tests.
- Added cross-catalog and same-catalog composition tests.
- Added Python 3.10 and 3.11 CI checks.
- Required 100% statement and branch coverage.

### Security

- Output filenames are reduced to their basename before files are written.
- The Docker container runs as an unprivileged user.
- Remote services and files may require their own credentials.

> [!IMPORTANT]
> Validation checks metadata only. It does not confirm that a remote asset is
> available or that the client has permission to access it.

Catalog URLs and collection snapshots are stored in
`src/geocr_mcp_server/config/catalogs.yaml`. Set `GEOCR_CATALOGS_CONFIG` to use
another YAML registry without changing Python code.

[1.0.0]: https://github.com/HarshShinde0/geocr_mcp/releases/tag/v1.0.0
