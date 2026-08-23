# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-08-23

First stable release. This is where it all comes together: an MCP server that
lets any LLM agent work with GeoCroissant metadata - discover Earth-observation datasets, turn them into standards-conformant
GeoCroissant documents, validate them, and actually read the data behind them.

Everything under the hood is done by the official library, installed
straight from the GeoCroissant fork, so there is zero re-implementation of the
spec here.

### Added

- **EO dataset discovery.** Live STAC search against the Element84 Earth
  Search API (`https://earth-search.aws.element84.com/v1`), with three tools:
  `list_eo_catalogs` for registered catalogs,`search_eo_datasets` for /topic search over collections
  and `search_eo_scenes` for spatial/temporal/cloud-cover scene search in a
  bounding box, with per-scene ids, dates, cloud cover and native EPSG.

- **STAC to GeoCroissant generation.** The tool,
  `create_geocroissant_from_stac`, runs the full pipeline end to end:
  search results come back as a validated GeoCroissant JSON-LD document with
  schema.org coverage, CRS, band configuration and spectral metadata derived
  from `eo:bands` (converted from micrometers to nanometers), distribution
  FileObjects pointing at the real asset URLs, and a RecordSet embedding one
  row per scene so records can be previewed without downloading anything.

- **The validator as a tool.** `validate_croissant` accepts a file
  path, URL or inline JSON document and returns structured pass/fail reports -
  the same engine behind `mlcroissant validate`.

- **inspection.** `inspect_geocroissant` summarizes core metadata plus
  every GeoCroissant property: CRS, spatial/temporal resolution, band
  configuration, record endpoint, spatial index/bias/sampling strategy.

- **Structure graph** `get_structure_graph` exposes the directed
  multigraph the library builds internally (Metadata / FileObject / FileSet /
  RecordSet / Field nodes; source, join and containment edges) for lineage
  and dependency analysis.

- **Record materialization.** `get_records_preview` executes the real
  operation graph - downloads, extracts, transforms - exactly like
  `Dataset.records(...)` in Python, with optional filters and a small limit
  for safety.

- **Distribution URLs and scaffolding.** `extract_distribution_urls` pulls
  downloadable URLs (with formats and checksums) from the distribution;
  `create_geocroissant_scaffold` generates a validated GeoCroissant document
  from structured parameters alone - no network needed - and checks it through
  the real validator before handing it over.

- **Built-in spec reference.** `get_geocroissant_spec_reference` answers
  questions about the spec itself: namespaces, every `geocr:` property with
  domains and cardinality, the canonical `@context`, a sample document and
  the Python API.

- **Data-driven catalog registry.** Catalogs, modalities, topics and default
  cloud cover live in `config/catalogs.yaml`. Point `GEOCR_CATALOGS_CONFIG`
  at your own copy to register another catalog without touching code; the
  loader validates topic references at startup so typos fail fast.

- **Solid foundations.** `FastMCP`-based server following the awslabs/mcp
  conventions (tools class with `register(mcp)`, pydantic response models,
  rich docstrings); stdio transport by default with sse/streamable-http for
  hosted deployments; Dockerfile with healthcheck; unit tests covering every
  tool without requiring network access.

### Changed

- Generated files are written inside `GEOCR_OUTPUT_DIR` (system temp dir by
  default), with filenames reduced to their basename so path traversal is
  blocked.

### Security

- The server only makes network requests when a tool input references a URL
  or when materializing records from remote distributions. Run containers as
  non-root (the provided Dockerfile already does).

[1.0.0]: https://github.com/HarshShinde0/geocr_mcp/releases/tag/v1.0.0
