"""Croissant / GeoCroissant tools for the MCP server.

Every tool is a thin, well-documented wrapper around the official
``mlcroissant`` Python library. The library performs all parsing, static
analysis (structure graph), validation and record materialization; these
tools only adapt its inputs/outputs for LLM consumption.
"""

import asyncio
import json as json_lib
from geocr_mcp_server import common, eo, reference, spec
from geocr_mcp_server.models import (
    DistributionUrls,
    RecordsPreview,
    ScaffoldResult,
    StructureGraph,
    ValidationReport,
)
from loguru import logger
from mcp.server.fastmcp import Context
from pydantic import Field
from typing import Annotated, Any


MAX_RECORDS_LIMIT = 100


class GeoCroissantTools:
    """Croissant / GeoCroissant tools exposed through the MCP server."""

    def register(self, mcp) -> None:
        """Registers all tools with the MCP server."""
        mcp.tool(name='list_eo_catalogs')(self.list_eo_catalogs)
        mcp.tool(name='search_eo_datasets')(self.search_eo_datasets)
        mcp.tool(name='search_eo_scenes')(self.search_eo_scenes)
        mcp.tool(name='validate_croissant')(self.validate_croissant)
        mcp.tool(name='inspect_geocroissant')(self.inspect_geocroissant)
        mcp.tool(name='get_structure_graph')(self.get_structure_graph)
        mcp.tool(name='list_record_sets')(self.list_record_sets)
        mcp.tool(name='get_records_preview')(self.get_records_preview)
        mcp.tool(name='extract_distribution_urls')(self.extract_distribution_urls)
        mcp.tool(name='create_geocroissant_scaffold')(self.create_geocroissant_scaffold)
        mcp.tool(name='create_geocroissant_from_stac')(self.create_geocroissant_from_stac)
        mcp.tool(name='get_geocroissant_spec_reference')(self.get_geocroissant_spec_reference)

    # ------------------------------------------------------------------
    # 0. EO dataset discovery (STAC)
    # ------------------------------------------------------------------

    async def list_eo_catalogs(self, ctx: Context) -> dict[str, Any]:
        """Lists the Earth observation STAC catalogs registered on this server.

        The registry is data-driven (config/catalogs.yaml): today it contains
        Element84 Earth Search over AWS Open Data
        (https://earth-search.aws.element84.com/v1) with its searchable
        modalities, curated collections and topic keywords.

        Usage: Call once to see where EO data can be discovered from before
        using `search_eo_datasets` / `search_eo_scenes`.

        Returns:
        --------
        Dictionary containing:
            - catalogs: Registered catalogs with id, name, URL, description,
              modalities, common collections and supported topics.
        """
        del ctx
        return {'catalogs': eo.list_catalogs()}

    async def search_eo_datasets(
        self,
        ctx: Context,
        query: Annotated[
            str,
            Field(
                description=(
                    "Free-text query. Topics like 'flood', 'wildfire', 'ndvi', "
                    "'urban' resolve to curated collections; other words "
                    'keyword-match collection metadata. Empty lists all.'
                )
            ),
        ] = '',
        modality: Annotated[
            str | None,
            Field(description='Filter by sensor modality: optical | radar | elevation.'),
        ] = None,
    ) -> dict[str, Any]:
        """Searches Earth observation DATASETS (STAC collections) by keyword.

        Performs collection-level search on the Earth Search STAC API
        (AWS Open Data). Queries hit the topics map first ('flood' -> Sentinel-1
        + Sentinel-2, 'dem' -> Copernicus DEM...), then fall back to keyword
        matching against live collection metadata; every hit is classified by
        sensor modality (optical / radar / elevation).

        Usage: Start here for dataset-level discovery ("find me flood/burn
        scar/terrain datasets"). Then use the returned collection ids with
        `search_eo_scenes`, or jump straight to `create_geocroissant_from_stac`
        to get GeoCroissant metadata.

        Returns:
        --------
        Dictionary containing:
            - matched_topics: Topic-map hits for the query.
            - count: Number of matching collections found.
            - collections: Matches with catalog, collection id, title,
              description snippet, modality, license and temporal extent.
        """
        try:
            result = await asyncio.to_thread(eo.search_collections, query=query, modality=modality)
            await ctx.info(f"search_eo_datasets('{query}') -> {result['count']} hits")
            return result
        except ValueError as e:
            logger.warning(f'Invalid input for search_eo_datasets: {e}')
            await ctx.error(str(e))
            raise ValueError(str(e)) from e
        except Exception as e:
            logger.error(f'Error in search_eo_datasets: {e}')
            await ctx.error(f'Error searching EO datasets: {e}')
            raise

    async def search_eo_scenes(
        self,
        ctx: Context,
        bbox: Annotated[
            list[float],
            Field(description='Bounding box as [min_lon, min_lat, max_lon, max_lat].'),
        ],
        collections: Annotated[
            list[str] | None,
            Field(
                description='Explicit STAC collection ids. Defaults to curated '
                'collections for the chosen modality.'
            ),
        ] = None,
        modality: Annotated[
            str | None,
            Field(description='Modality used to pick default collections.'),
        ] = None,
        datetime_range: Annotated[
            str | None,
            Field(description='STAC datetime interval, e.g. "2023-06-01/2023-09-30".'),
        ] = None,
        max_cloud_cover: Annotated[
            float | None,
            Field(
                description='Maximum eo:cloud_cover percentage for optical scenes '
                '(ignored when None).'
            ),
        ] = None,
        limit: Annotated[int, Field(description='Max scenes returned (1-50).')] = 10,
    ) -> dict[str, Any]:
        """Searches satellite SCENES inside a bounding box on Earth Search.

        Executes a real STAC item search (pystac-client) against
        https://earth-search.aws.element84.com/v1 filtered by spatial extent,
        time range and cloud cover. Scenes are the individual acquisitions
        (tiles/granules) that become records of a GeoCroissant dataset.

        Usage: Use after `search_eo_datasets` (or directly with known
        collections) to check actual data availability for an area of interest.
        Feed promising results into `create_geocroissant_from_stac`.

        Returns:
        --------
        Dictionary containing:
            - scene_count and scenes: Per-scene id, collection, acquisition
              datetime, platform, cloud cover, native EPSG and asset keys.
        """
        try:

            def _search():
                result = eo.search_scenes(
                    bbox=bbox,
                    collections=collections,
                    modality=modality,
                    datetime_range=datetime_range,
                    max_cloud_cover=max_cloud_cover,
                    limit=limit,
                )
                result.pop('_raw_items', None)
                return result

            result = await asyncio.to_thread(_search)
            await ctx.info(
                f'search_eo_scenes -> {result["scene_count"]} scene(s) from '
                f'{result["collections_searched"]}'
            )
            return result
        except ValueError as e:
            logger.warning(f'Invalid input for search_eo_scenes: {e}')
            await ctx.error(str(e))
            raise ValueError(str(e)) from e
        except Exception as e:
            logger.error(f'Error in search_eo_scenes: {e}')
            await ctx.error(f'Error searching EO scenes: {e}')
            raise

    async def create_geocroissant_from_stac(
        self,
        ctx: Context,
        name: Annotated[str, Field(description='Name for the generated dataset.')],
        bbox: Annotated[
            list[float],
            Field(description='Bounding box as [min_lon, min_lat, max_lon, max_lat].'),
        ],
        collections: Annotated[
            list[str] | None, Field(description='Explicit STAC collection ids.')
        ] = None,
        modality: Annotated[
            str | None, Field(description='Modality used to pick default collections.')
        ] = None,
        datetime_range: Annotated[str | None, Field(description='STAC datetime interval.')] = None,
        max_cloud_cover: Annotated[
            float | None, Field(description='Max cloud cover percentage.')
        ] = 20,
        limit: Annotated[int, Field(description='Number of scenes to include (1-50).')] = 5,
        description: Annotated[
            str, Field(description='Description of the generated dataset.')
        ] = '',
        license: Annotated[str, Field(description='License URL.')] = '',
        creators: Annotated[list[str] | None, Field(description='Creator names.')] = None,
        output_filename: Annotated[
            str,
            Field(
                description='When provided, writes the validated JSON-LD into '
                'GEOCR_OUTPUT_DIR (or temp dir) and returns the path.'
            ),
        ] = '',
    ) -> dict[str, Any]:
        """Searches live EO data and generates VALIDATED GeoCroissant metadata from it.

        This is the flagship end-to-end pipeline of this server:

        1. Runs a real STAC search (bbox + collections + datetime + cloud cover).
        2. Derives GeoCroissant properties from the results: schema.org spatial/
           temporal coverage, CRS (EPSG:4326), record endpoint, band
           configuration and spectral band metadata from `eo:bands`
           (micrometers converted to nanometers), distribution FileObjects for
           direct asset URLs, and a RecordSet with one inline row per scene.
        3. Validates the document through the official `mlcroissant` library
           before returning it.

        Usage: THE tool for turning discovered EO data into GeoCroissant.
        After generation use `inspect_geocroissant`, `get_records_preview`
        and `extract_distribution_urls` on the output.

        Returns:
        --------
        Dictionary containing:
            - valid/errors/warnings: mlcroissant validation outcome.
            - json_ld: The generated GeoCroissant document.
            - path: Output file path when output_filename was given.
            - search_summary: What was searched and how many scenes matched.
        """

        def _generate():
            search = eo.search_scenes(
                bbox=bbox,
                collections=collections,
                modality=modality,
                datetime_range=datetime_range,
                max_cloud_cover=max_cloud_cover,
                limit=limit,
            )
            raw_items = search.pop('_raw_items')
            doc = eo.geocroissant_from_stac(
                name=name.strip(),
                description=description,
                license_url=license,
                creators=creators or [],
                raw_items=raw_items,
            )
            validation = self._validate_sync(doc)
            path = None
            if output_filename:
                path = str(common.write_json_ld(doc, common.secure_output_path(output_filename)))
            return {
                **validation,
                'json_ld': doc,
                'path': path,
                'search_summary': {
                    'catalog': search['catalog'],
                    'collections_searched': search['collections_searched'],
                    'bbox': search['bbox'],
                    'datetime_range': datetime_range,
                    'scene_count': search['scene_count'],
                },
            }

        try:
            result = await asyncio.to_thread(_generate)
            status = 'passed' if result['valid'] else 'FAILED'
            await ctx.info(
                f'GeoCroissant `{name}` from {result["search_summary"]["scene_count"]}'
                f' scene(s): validation {status}'
            )
            return result
        except ValueError as e:
            logger.warning(f'Cannot generate GeoCroissant from STAC: {e}')
            await ctx.error(str(e))
            raise ValueError(str(e)) from e
        except Exception as e:
            logger.error(f'Error in create_geocroissant_from_stac: {e}')
            await ctx.error(f'Error generating GeoCroissant from STAC: {e}')
            raise

    # ------------------------------------------------------------------
    # 1. Validation
    # ------------------------------------------------------------------

    async def validate_croissant(
        self,
        ctx: Context,
        jsonld_path: Annotated[
            str,
            Field(description='Path to a local Croissant/GeoCroissant JSON(-LD) file.'),
        ] = '',
        jsonld_url: Annotated[
            str,
            Field(description='URL of a Croissant/GeoCroissant JSON-LD document.'),
        ] = '',
        jsonld_content: Annotated[
            str,
            Field(description='Raw JSON string of a Croissant/GeoCroissant document.'),
        ] = '',
    ) -> dict[str, Any]:
        """Validates a Croissant or GeoCroissant JSON-LD document.

        Runs the official MLCommons ``mlcroissant`` validator: JSON syntax check,
        JSON-LD expansion, structure-graph construction (FileObjects/FileSets,
        RecordSets, Fields, sources & joins) and full schema conformance checks.

        Usage: Call this tool whenever a dataset description is created or edited,
        BEFORE publishing it, and after any modification of an existing file.
        Works for both plain Croissant documents and documents using the
        GeoCroissant extension (`geocr:` properties).

        Returns:
        --------
        Dictionary containing:
            - valid: True when the document passes validation.
            - errors: Blocking errors reported by the library (empty when valid).
            - warnings: Non-blocking recommendations (e.g. missing license).
            - is_geospatial: Whether GeoCroissant conformance is declared.
            - conforms_to / dataset_name: Extracted metadata when loadable.
        """
        try:
            source_arg = common.resolve_jsonld_input(
                jsonld_content=jsonld_content or None,
                jsonld_path=jsonld_path or None,
                jsonld_url=jsonld_url or None,
            )
        except json_lib.JSONDecodeError as e:
            # Unparseable inline content is a validation failure, not a tool error.
            return ValidationReport(
                valid=False,
                source='inline JSON content',
                errors=[f'JSONDecodeError: {e}'],
            ).model_dump()
        except ValueError as e:
            # Input resolution problems are user-facing; report, don't raise.
            logger.warning(f'Invalid input for validate_croissant: {e}')
            await ctx.error(str(e))
            raise ValueError(str(e)) from e
        except Exception as e:
            logger.error(f'Error in validate_croissant: {e}')
            await ctx.error(f'Error validating Croissant document: {e}')
            raise
        return await asyncio.to_thread(self._validate_sync, source_arg)

    def _validate_sync(self, source: dict[str, Any] | str) -> dict[str, Any]:
        """Runs mlcroissant static analysis synchronously."""
        from mlcroissant import ValidationError

        source_desc = 'inline JSON content' if isinstance(source, dict) else str(source)
        report = {
            'valid': False,
            'source': source_desc,
            'errors': [],
            'warnings': [],
            'conforms_to': [],
            'is_geospatial': False,
            'dataset_name': None,
        }
        try:
            dataset = common.load_dataset(source)
        except ValidationError as e:
            report['errors'] = [line for line in str(e).splitlines() if line.strip()]
            return report
        except Exception as e:
            # Malformed JSON-LD contexts, unreadable inputs, network failures...
            report['errors'] = [f'{type(e).__name__}: {e}']
            return report
        metadata = dataset.metadata
        summary = common.summarize_metadata(metadata)
        report.update(
            {
                'valid': True,
                'dataset_name': summary.get('name'),
                'conforms_to': summary.get('conformsTo', []),
                'is_geospatial': any(
                    'croissant/geo' in str(c) for c in summary.get('conformsTo', [])
                ),
                'errors': sorted(metadata.ctx.issues.errors),
                'warnings': sorted(metadata.ctx.issues.warnings),
            }
        )
        return report

    # ------------------------------------------------------------------
    # 2. Inspection
    # ------------------------------------------------------------------

    async def inspect_geocroissant(
        self,
        ctx: Context,
        jsonld_path: Annotated[
            str, Field(description='Path to a local Croissant/GeoCroissant file.')
        ] = '',
        jsonld_url: Annotated[
            str, Field(description='URL of a Croissant/GeoCroissant JSON-LD document.')
        ] = '',
        jsonld_content: Annotated[
            str, Field(description='Raw JSON string of a Croissant document.')
        ] = '',
    ) -> dict[str, Any]:
        """Inspects a Croissant/GeoCroissant document and returns a structured summary.

        Parses the document through the ``mlcroissant`` library (which also acts as
        a strict syntax/schema check - invalid documents are rejected) and returns
        a structured digest: core metadata, GeoCroissant extension properties
        (CRS, resolutions, band configuration, spectral bands, record endpoint...),
        distribution entries (FileObjects/FileSets with URLs, formats, hashes),
        and every RecordSet with its Fields (data types, array shapes,
        source/extract/transform chains).

        Usage: Use this tool to READ and UNDERSTAND a dataset description before
        consuming it, comparing datasets, or planning how to load records.

        Returns:
        --------
        Dictionary containing:
            - name/description/license/version/conformsTo and other core metadata.
            - geospatial: All declared `geocr:` extension properties.
            - distribution: FileObject/FileSet entries.
            - record_sets: RecordSets with nested fields and geo properties.
        """
        try:
            source_arg = common.resolve_jsonld_input(
                jsonld_content=jsonld_content or None,
                jsonld_path=jsonld_path or None,
                jsonld_url=jsonld_url or None,
            )
        except (ValueError, FileNotFoundError) as e:
            logger.warning(f'Invalid input for inspect_geocroissant: {e}')
            await ctx.error(str(e))
            raise ValueError(str(e)) from e
        try:

            def _inspect():
                dataset = common.load_dataset(source_arg)
                return common.summarize_metadata(dataset.metadata)

            summary = await asyncio.to_thread(_inspect)
            await ctx.info(
                f'Inspecting `{summary.get("name")}` '
                f'({len(summary.get("record_sets", []))} record sets)'
            )
            return summary
        except Exception as e:
            logger.error(f'Error in inspect_geocroissant: {e}')
            await ctx.error(f'Error inspecting Croissant document: {e}')
            raise

    # ------------------------------------------------------------------
    # 3. Structure graph
    # ------------------------------------------------------------------

    async def get_structure_graph(
        self,
        ctx: Context,
        jsonld_path: Annotated[
            str, Field(description='Path to a local Croissant/GeoCroissant file.')
        ] = '',
        jsonld_url: Annotated[
            str, Field(description='URL of a Croissant/GeoCroissant JSON-LD document.')
        ] = '',
        jsonld_content: Annotated[
            str, Field(description='Raw JSON string of a Croissant document.')
        ] = '',
    ) -> StructureGraph:
        """Extracts the internal structure graph of a Croissant document.

        Builds the directed multigraph that ``mlcroissant`` uses internally for
        static analysis: nodes are Metadata / FileObject / FileSet / RecordSet /
        Field objects and edges connect fields to their data sources, record sets
        to their fields, files to archives they are contained in, and referenced
        (foreign-key) fields.

        Usage: Use this tool to reason about dataset lineage and dependencies,
        e.g. "which files feed this field?", "what does this join look like?",
        or to explain a dataset's architecture before writing loading code.

        Returns:
        --------
        StructureGraph containing:
            - nodes: Every node with @id, type, name and parent @id.
            - edges: Directed edges as {source, target} @id pairs.
        """
        try:
            source_arg = common.resolve_jsonld_input(
                jsonld_content=jsonld_content or None,
                jsonld_path=jsonld_path or None,
                jsonld_url=jsonld_url or None,
            )
        except (ValueError, FileNotFoundError) as e:
            logger.warning(f'Invalid input for get_structure_graph: {e}')
            await ctx.error(str(e))
            raise ValueError(str(e)) from e

        def _build_graph() -> StructureGraph:
            dataset = common.load_dataset(source_arg)
            graph = dataset.metadata.ctx.graph
            nodes = []
            for node in graph.nodes:
                entry = {
                    '@id': node.uuid,
                    'type': common.node_type_name(node),
                    'name': common._language_value(getattr(node, 'name', '')) or node.uuid,
                }
                parents = list(getattr(node, 'parents', []) or [])
                if parents:
                    entry['parent'] = parents[-1].uuid
                nodes.append(entry)
            edges = [{'source': u.uuid, 'target': v.uuid} for u, v, _ in graph.edges]
            # Deterministic output ordering.
            nodes.sort(key=lambda n: (n['type'], n['@id']))
            edges.sort(key=lambda e: (e['source'], e['target']))
            return StructureGraph(
                node_count=len(nodes),
                edge_count=len(edges),
                nodes=nodes,
                edges=edges,
            )

        try:
            result = await asyncio.to_thread(_build_graph)
            await ctx.info(
                f'Structure graph: {result.node_count} nodes, {result.edge_count} edges'
            )
            return result
        except Exception as e:
            logger.error(f'Error in get_structure_graph: {e}')
            await ctx.error(f'Error building structure graph: {e}')
            raise

    # ------------------------------------------------------------------
    # 4. Record sets listing
    # ------------------------------------------------------------------

    async def list_record_sets(
        self,
        ctx: Context,
        jsonld_path: Annotated[
            str, Field(description='Path to a local Croissant/GeoCroissant file.')
        ] = '',
        jsonld_url: Annotated[
            str, Field(description='URL of a Croissant/GeoCroissant JSON-LD document.')
        ] = '',
        jsonld_content: Annotated[
            str, Field(description='Raw JSON string of a Croissant document.')
        ] = '',
    ) -> list[dict[str, Any]]:
        """Lists the RecordSets of a Croissant/GeoCroissant document.

        A RecordSet is a collection of records (rows/examples) produced by
        applying the declared extraction pipeline to the distribution. This tool
        returns each RecordSet's @id, name, description, key fields, enumeration
        flag, number of inline records/examples and its Fields with their data
        types and source chains.

        Usage: Call this tool to discover what data a dataset exposes and which
        RecordSet names to pass to `get_records_preview`.

        Returns:
        --------
        List of dictionaries, one per RecordSet, each including:
            - @id: The RecordSet identifier used by other tools.
            - fields: Nested field summaries (dataType, isArray/arrayShape,
              source extract/transform chain, geo band properties).
        """
        try:
            source_arg = common.resolve_jsonld_input(
                jsonld_content=jsonld_content or None,
                jsonld_path=jsonld_path or None,
                jsonld_url=jsonld_url or None,
            )
        except (ValueError, FileNotFoundError) as e:
            logger.warning(f'Invalid input for list_record_sets: {e}')
            await ctx.error(str(e))
            raise ValueError(str(e)) from e

        def _list() -> list[dict[str, Any]]:
            dataset = common.load_dataset(source_arg)
            return [common.summarize_record_set(rs) for rs in dataset.metadata.record_sets]

        try:
            record_sets = await asyncio.to_thread(_list)
            await ctx.info(f'Found {len(record_sets)} record set(s)')
            return record_sets
        except Exception as e:
            logger.error(f'Error in list_record_sets: {e}')
            await ctx.error(f'Error listing record sets: {e}')
            raise

    # ------------------------------------------------------------------
    # 5. Records preview
    # ------------------------------------------------------------------

    async def get_records_preview(
        self,
        ctx: Context,
        record_set: Annotated[
            str,
            Field(
                description=(
                    'The @id of the RecordSet to read (see `list_record_sets` for available ids).'
                )
            ),
        ],
        limit: Annotated[
            int,
            Field(description=f'Maximum number of records to return (1-{MAX_RECORDS_LIMIT}).'),
        ] = 5,
        filters: Annotated[
            dict[str, str] | None,
            Field(
                description=(
                    'Optional single-entry filter {field_id: value}, e.g. '
                    '{"my_recordset/split": "train"} (only supported for fields '
                    'extracted via regex transformations).'
                )
            ),
        ] = None,
        jsonld_path: Annotated[
            str, Field(description='Path to a local Croissant/GeoCroissant file.')
        ] = '',
        jsonld_url: Annotated[
            str, Field(description='URL of a Croissant/GeoCroissant JSON-LD document.')
        ] = '',
        jsonld_content: Annotated[
            str, Field(description='Raw JSON string of a Croissant document.')
        ] = '',
    ) -> RecordsPreview:
        """Materializes the first records of a RecordSet by executing the data pipeline.

        This tool runs the real ``mlcroissant`` operation graph: it downloads (or
        resolves locally) the declared FileObjects/FileSets, applies extracts and
        transforms, and yields actual records - exactly what
        ``Dataset.records(record_set)`` yields in Python.

        Usage: Use it to preview/sample a dataset's actual data before writing
        training code, or to sanity-check that a generated Croissant description
        produces the expected columns and values.

        IMPORTANT: For remote distributions this may download data; keep `limit`
        small on large datasets. Datasets with inline `cr:data` return those rows
        directly without downloads.

        Returns:
        --------
        RecordsPreview containing:
            - record_set: The RecordSet @id that was read.
            - columns: Column names found across returned records.
            - rows: List of records keyed by fully-qualified field ids.
            - truncated: True if more records exist beyond `limit`.
        """
        limit = max(1, min(limit, MAX_RECORDS_LIMIT))
        try:
            source_arg = common.resolve_jsonld_input(
                jsonld_content=jsonld_content or None,
                jsonld_path=jsonld_path or None,
                jsonld_url=jsonld_url or None,
            )
        except (ValueError, FileNotFoundError) as e:
            logger.warning(f'Invalid input for get_records_preview: {e}')
            await ctx.error(str(e))
            raise ValueError(str(e)) from e

        def _read() -> RecordsPreview:
            from mlcroissant import Dataset as MlcDataset

            dataset = MlcDataset(jsonld=source_arg)
            rows = []
            columns: list[str] = []
            for row in dataset.records(record_set=record_set, filters=filters):
                safe_row = {}
                for k, v in row.items():
                    key = str(k)
                    if key not in columns:
                        columns.append(key)
                    safe_row[key] = common.to_json_safe(v)
                rows.append(safe_row)
                if len(rows) >= limit:
                    break
            return RecordsPreview(
                record_set=record_set,
                columns=columns,
                rows=rows,
                num_records=len(rows),
                truncated=len(rows) >= limit,
            )

        try:
            preview = await asyncio.to_thread(_read)
            await ctx.info(f'Read {preview.num_records} record(s) from `{record_set}`')
            return preview
        except Exception as e:
            logger.error(f'Error in get_records_preview: {e}')
            await ctx.error(f'Error reading records from `{record_set}`: {e}')
            raise

    # ------------------------------------------------------------------
    # 6. Distribution URLs
    # ------------------------------------------------------------------

    async def extract_distribution_urls(
        self,
        ctx: Context,
        jsonld_path: Annotated[
            str, Field(description='Path to a local Croissant/GeoCroissant file.')
        ] = '',
        jsonld_url: Annotated[
            str, Field(description='URL of a Croissant/GeoCroissant JSON-LD document.')
        ] = '',
        jsonld_content: Annotated[
            str, Field(description='Raw JSON string of a Croissant document.')
        ] = '',
    ) -> DistributionUrls:
        """Extracts downloadable URLs from a Croissant document's distribution.

        Collects the `contentUrl` of every FileObject together with its encoding
        formats, sizes and checksums, plus FileSet include patterns and archive
        containers. These are the direct access points for the dataset bytes.

        Usage: Use this tool to obtain concrete download links (e.g. GeoTIFF /
        COG / ZIP assets) for ingestion code without parsing the JSON manually.

        Returns:
        --------
        DistributionUrls containing:
            - urls: One entry per distribution item (name, type, contentUrl,
              encodingFormat, md5/sha256, includes/containedIn when present).
            - count: Number of distribution items with at least one URL.
        """
        try:
            source_arg = common.resolve_jsonld_input(
                jsonld_content=jsonld_content or None,
                jsonld_path=jsonld_path or None,
                jsonld_url=jsonld_url or None,
            )
        except (ValueError, FileNotFoundError) as e:
            logger.warning(f'Invalid input for extract_distribution_urls: {e}')
            await ctx.error(str(e))
            raise ValueError(str(e)) from e

        def _extract() -> DistributionUrls:
            dataset = common.load_dataset(source_arg)
            urls = []
            for entry in common.summarize_distribution(dataset.metadata):
                if entry.get('contentUrl') or entry.get('includes'):
                    urls.append(entry)
            return DistributionUrls(urls=urls, count=len(urls))

        try:
            result = await asyncio.to_thread(_extract)
            await ctx.info(f'Extracted URLs for {result.count} distribution item(s)')
            return result
        except Exception as e:
            logger.error(f'Error in extract_distribution_urls: {e}')
            await ctx.error(f'Error extracting distribution URLs: {e}')
            raise

    # ------------------------------------------------------------------
    # 7. Scaffold generation
    # ------------------------------------------------------------------

    async def create_geocroissant_scaffold(
        self,
        ctx: Context,
        name: Annotated[str, Field(description='Name of the dataset.')],
        description: Annotated[str, Field(description='Description of the dataset.')] = '',
        license: Annotated[
            str,
            Field(
                description='License URL, preferably SPDX, e.g. '
                '"https://creativecommons.org/licenses/by/4.0/".'
            ),
        ] = '',
        version: Annotated[str, Field(description='Dataset version, e.g. "1.0".')] = '',
        date_published: Annotated[str, Field(description='Publication date as YYYY-MM-DD.')] = '',
        creators: Annotated[
            list[str] | None,
            Field(description='Creator names (rendered as sc:Organization entries).'),
        ] = None,
        bbox: Annotated[
            list[float] | None,
            Field(
                description=(
                    'Spatial coverage as [min_lon, min_lat, max_lon, max_lat] in '
                    'EPSG:4326 (standard GIS order).'
                )
            ),
        ] = None,
        temporal_coverage: Annotated[
            str | None,
            Field(description='Temporal coverage interval, e.g. "2018-01-01/2021-12-31".'),
        ] = None,
        coordinate_reference_system: Annotated[
            str,
            Field(description='CRS identifier, e.g. "EPSG:4326".'),
        ] = '',
        spatial_resolution: Annotated[
            float | None,
            Field(description='Ground sampling distance value (with unit below).'),
        ] = None,
        spatial_resolution_unit: Annotated[
            str, Field(description='Unit for spatial_resolution, e.g. "m".')
        ] = 'm',
        temporal_resolution_value: Annotated[
            float | int | None,
            Field(description='Revisit cadence value (with unit below).'),
        ] = None,
        temporal_resolution_unit: Annotated[
            str, Field(description='Unit for temporal cadence, e.g. "days".')
        ] = 'days',
        band_names: Annotated[
            list[str] | None,
            Field(description='Ordered raster band names, e.g. ["Blue","Green","Red","NIR"].'),
        ] = None,
        spectral_bands: Annotated[
            list[dict[str, Any]] | None,
            Field(
                description=(
                    'Per-band spectral metadata entries like {"name": "Blue", '
                    '"centerWavelength": {"value": 490, "unitText": "nm"}, '
                    '"bandwidth": {...}}.'
                )
            ),
        ] = None,
        file_sets: Annotated[
            list[dict[str, Any]] | None,
            Field(
                description=(
                    'List of FileSet specs: {"id": "images", "name": "Images", '
                    '"encoding_format": "image/tiff", "includes": "images/**/*.tif"}.'
                )
            ),
        ] = None,
        file_objects: Annotated[
            list[dict[str, Any]] | None,
            Field(
                description=(
                    'List of FileObject specs: {"id": "data.zip", "name": "data.zip", '
                    '"content_url": "https://...", "encoding_format": "application/zip", '
                    '"sha256": "...", "md5": "..."}.'
                )
            ),
        ] = None,
        record_set_name: Annotated[
            str | None, Field(description='Name/@id of the scaffolded RecordSet.')
        ] = 'records',
        record_set_description: Annotated[
            str, Field(description='Description of the scaffolded RecordSet.')
        ] = '',
        field_name: Annotated[
            str,
            Field(description='Name of the main data Field inside the RecordSet.'),
        ] = 'data',
        field_data_type: Annotated[
            str,
            Field(description='Field dataType, e.g. "sc:ImageObject", "sc:Text", "sc:URL".'),
        ] = 'sc:ImageObject',
        field_is_array: Annotated[
            bool, Field(description='Whether the main Field is an array (raster/tensor).')
        ] = False,
        field_array_shape: Annotated[
            str | None,
            Field(
                description='Array shape as comma-separated dims, e.g. "512,512,6" '
                '(requires field_is_array=True).'
            ),
        ] = None,
        source_file_set_id: Annotated[
            str | None,
            Field(
                description='@id of the FileSet/FileObject the main Field reads from. '
                'Defaults to the first declared distribution entry.'
            ),
        ] = None,
        cite_as: Annotated[
            str, Field(description='Citation (BibTeX or URL) for the dataset.')
        ] = '',
        output_filename: Annotated[
            str,
            Field(
                description=(
                    'When provided, writes the validated JSON-LD to this filename '
                    'inside GEOCR_OUTPUT_DIR (or the system temp dir) and returns '
                    'the path.'
                )
            ),
        ] = '',
    ) -> ScaffoldResult:
        """Generates a validated GeoCroissant JSON-LD scaffold from parameters.

        Produces a standards-conformant starting point modeled on the official
        GeoCroissant example: correct @context (including the `geocr` prefix),
        dual conformance (`croissant/1.1` + `geocr`), schema.org spatial/temporal
        coverage, GeoCroissant properties (CRS, resolutions, band configuration,
        spectral bands), distribution entries and a RecordSet wired to them via
        proper cr:source/cr:extract declarations.

        The generated document is then parsed and checked by the real
        ``mlcroissant`` validator, so `valid=True` means the scaffold already
        passes the official library checks.

        Usage: Call FIRST when creating new dataset metadata, then edit the
        returned JSON-LD for domain specifics and re-check with
        `validate_croissant`. Use `inspect_geocroissant` afterwards to review it.

        Returns:
        --------
        ScaffoldResult containing:
            - valid: Whether the scaffold passed mlcroissant validation.
            - json_ld: The generated document.
            - errors/warnings: Library messages when not fully clean.
            - path: Output file path when output_filename was given.
        """
        try:
            scaffold = spec.build_scaffold(
                name=name,
                description=description,
                license=license,
                cite_as=cite_as,
                version=version,
                date_published=date_published,
                creators=creators or [],
                bbox=bbox,
                temporal_coverage=temporal_coverage,
                coordinate_reference_system=coordinate_reference_system,
                spatial_resolution=spatial_resolution,
                spatial_resolution_unit=spatial_resolution_unit,
                temporal_resolution_value=temporal_resolution_value,
                temporal_resolution_unit=temporal_resolution_unit,
                band_names=band_names,
                spectral_bands=spectral_bands,
                file_sets=file_sets,
                file_objects=file_objects,
                record_set_name=record_set_name,
                record_set_description=record_set_description,
                field_name=field_name,
                field_data_type=field_data_type,
                field_is_array=field_is_array,
                field_array_shape=field_array_shape,
                source_file_set_id=source_file_set_id,
            )
        except ValueError as e:
            logger.warning(f'Invalid scaffold parameters: {e}')
            await ctx.error(str(e))
            raise ValueError(str(e)) from e

        path: str | None = None

        def _finalize() -> ScaffoldResult:
            nonlocal path
            validation = self._validate_sync(scaffold)
            if output_filename:
                out_path = common.write_json_ld(
                    scaffold, common.secure_output_path(output_filename)
                )
                path = str(out_path)
            return ScaffoldResult(
                valid=validation['valid'],
                json_ld=scaffold,
                errors=validation['errors'],
                warnings=validation['warnings'],
                path=path,
            )

        try:
            result = await asyncio.to_thread(_finalize)
            level = 'passed' if result.valid else 'FAILED'
            await ctx.info(
                f'Scaffold `{name}` validation {level}' + (f'; written to {path}' if path else '')
            )
            return result
        except Exception as e:
            logger.error(f'Error in create_geocroissant_scaffold: {e}')
            await ctx.error(f'Error generating GeoCroissant scaffold: {e}')
            raise

    # ------------------------------------------------------------------
    # 8. Spec reference
    # ------------------------------------------------------------------

    async def get_geocroissant_spec_reference(
        self,
        ctx: Context,
        topic: Annotated[
            str,
            Field(
                description=(
                    'Which part of the specification to return. One of: "overview", '
                    '"context" (@context snippet), "properties" (all geocr '
                    'properties), "example" (full sample document), '
                    '"python-api" (mlcroissant usage snippets), "all" (everything).'
                )
            ),
        ] = 'all',
    ) -> str:
        """Returns the GeoCroissant specification reference documentation.

        Provides the vocabulary cheat sheet distilled from the official GeoCroissant
        specification: namespace IRIs and prefixes, conformance declarations, every
        `geocr:` property with expected types/domains/cardinality, the canonical
        JSON-LD @context, a full sample document, and Python snippets for the
        ``mlcroissant`` API (load, validate, iterate records).

        Usage: Read this ONCE before authoring or editing GeoCroissant documents so
        property names, types and cardinalities match the specification exactly.
        Then use `create_geocroissant_scaffold` and `validate_croissant`.

        Returns:
        --------
        Markdown-formatted reference documentation for the requested topic.
        """
        del ctx  # No side effects; kept for FastMCP signature consistency.
        topic_normalized = (topic or 'all').strip().lower()
        if topic_normalized not in reference.TOPICS:
            raise ValueError(
                f'Unknown topic "{topic}". Choose one of: {sorted(reference.TOPICS)}.'
            )
        return reference.render_reference(topic_normalized)
