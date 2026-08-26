"""GeoCroissant tools exposed by the MCP server.

The server handles STAC discovery, geocoding, metadata conversion, and response
formatting. The configured ``mlcroissant`` package handles parsing,
validation, structure graphs, and record materialization.
"""

import asyncio
import json as json_lib
from geocr_mcp_server import common, composition, eo, geocoding, reference, spec
from geocr_mcp_server.models import (
    DistributionUrls,
    RecordsPreview,
    ScaffoldResult,
    StructureGraph,
    ValidationReport,
)
from loguru import logger
from mcp.server.fastmcp import Context
from operator import itemgetter
from pydantic import Field
from typing import Annotated, Any


MAX_RECORDS_LIMIT = 100


class GeoCroissantTools:
    """GeoCroissant tools exposed through the MCP server."""

    def register(self, mcp) -> None:
        """Registers all tools with the MCP server."""
        mcp.tool(name='ping')(self.ping)
        mcp.tool(name='list_eo_catalogs')(self.list_eo_catalogs)
        mcp.tool(name='search_eo_datasets')(self.search_eo_datasets)
        mcp.tool(name='get_eo_dataset_details')(self.get_eo_dataset_details)
        mcp.tool(name='geocode_place')(self.geocode_place)
        mcp.tool(name='count_eo_scenes')(self.count_eo_scenes)
        mcp.tool(name='search_eo_scenes')(self.search_eo_scenes)
        mcp.tool(name='validate_croissant')(self.validate_croissant)
        mcp.tool(name='inspect_geocroissant')(self.inspect_geocroissant)
        mcp.tool(name='get_structure_graph')(self.get_structure_graph)
        mcp.tool(name='list_record_sets')(self.list_record_sets)
        mcp.tool(name='get_records_preview')(self.get_records_preview)
        mcp.tool(name='extract_distribution_urls')(self.extract_distribution_urls)
        mcp.tool(name='create_geocroissant_scaffold')(self.create_geocroissant_scaffold)
        mcp.tool(name='create_geocroissant_from_stac')(self.create_geocroissant_from_stac)
        mcp.tool(name='create_geocroissant_from_stac_sources')(
            self.create_geocroissant_from_stac_sources
        )
        mcp.tool(name='get_geocroissant_spec_reference')(self.get_geocroissant_spec_reference)

    async def ping(self) -> str:
        """Returns pong to confirm that the MCP server is available."""
        return 'pong'

    # ------------------------------------------------------------------
    # 0. EO dataset discovery (STAC)
    # ------------------------------------------------------------------

    async def list_eo_catalogs(self, ctx: Context) -> dict[str, Any]:
        """Lists the Earth observation STAC catalogs registered on this server.

        The active YAML registry supplies each provider endpoint and an
        informational collection snapshot. Live discovery still queries the
        provider.
        """
        del ctx
        return {'catalogs': eo.list_catalogs()}

    async def search_eo_datasets(
        self,
        ctx: Context,
        catalog_id: Annotated[
            str | None,
            Field(description='Registered STAC catalog id. Defaults to earth-search.'),
        ] = None,
        limit: Annotated[
            int,
            Field(description='Maximum collections returned (1-500). Use 500 to inventory a catalog.'),
        ] = 15,
        offset: Annotated[
            int,
            Field(description='Zero-based collection offset for pagination.'),
        ] = 0,
    ) -> dict[str, Any]:
        """Lists Earth observation datasets represented by STAC collections.

        Reads collection metadata directly from the selected registered STAC
        API without keyword, topic or modality inference.

        Use returned collection IDs with `search_eo_scenes`, `count_eo_scenes`,
        or `create_geocroissant_from_stac`.
        """
        try:
            result = await asyncio.to_thread(
                eo.search_collections,
                limit=limit,
                offset=offset,
                catalog_id=catalog_id,
            )
            await ctx.info(f"search_eo_datasets -> {result['count']} collections")
            return result
        except ValueError as e:
            logger.warning(f'Invalid input for search_eo_datasets: {e}')
            await ctx.error(str(e))
            raise ValueError(str(e)) from e

    async def get_eo_dataset_details(
        self,
        ctx: Context,
        collection_id: Annotated[
            str,
            Field(description='Exact STAC collection id returned by search_eo_datasets.'),
        ],
        catalog_id: Annotated[
            str | None,
            Field(description='Registered STAC catalog id. Defaults to earth-search.'),
        ] = None,
    ) -> dict[str, Any]:
        """Returns provider metadata for one EO dataset.

        Use this after collection discovery so the LLM can inspect spatial and
        temporal extent, providers, bands, assets, summaries and links before
        selecting a collection for scene search.
        """
        try:
            result = await asyncio.to_thread(
                eo.get_collection_details,
                collection_id=collection_id,
                catalog_id=catalog_id,
            )
            await ctx.info(f'Loaded STAC metadata for `{collection_id}`')
            return result
        except ValueError as e:
            await ctx.error(str(e))
            raise ValueError(str(e)) from e

    async def geocode_place(
        self,
        ctx: Context,
        place_name: Annotated[
            str,
            Field(description='Human place name, such as "Delhi, India".'),
        ],
        limit: Annotated[int, Field(description='Maximum candidate locations (1-10).')] = 5,
    ) -> dict[str, Any]:
        """Resolves a human place name to candidate EPSG:4326 bounding boxes."""
        try:
            result = await asyncio.to_thread(geocoding.geocode_place, place_name, limit)
            await ctx.info(f'geocode_place -> {result["count"]} candidate(s)')
            return result
        except ValueError as e:
            await ctx.error(str(e))
            raise ValueError(str(e)) from e

    async def count_eo_scenes(
        self,
        ctx: Context,
        bbox: Annotated[
            list[float],
            Field(description='Bounding box as [min_lon, min_lat, max_lon, max_lat].'),
        ],
        collections: Annotated[
            list[str],
            Field(description='One or more explicit STAC collection ids.'),
        ],
        catalog_id: Annotated[
            str | None,
            Field(description='Registered STAC catalog id. Defaults to earth-search.'),
        ] = None,
        datetime_range: Annotated[
            str | None,
            Field(description='STAC datetime interval, e.g. "2023-01-01/2023-12-31".'),
        ] = None,
        max_cloud_cover: Annotated[
            float | None,
            Field(description='Optional maximum eo:cloud_cover percentage.'),
        ] = None,
    ) -> dict[str, Any]:
        """Counts matching scenes before requesting or generating records."""
        try:
            result = await asyncio.to_thread(
                eo.count_scenes,
                bbox=bbox,
                collections=collections,
                datetime_range=datetime_range,
                max_cloud_cover=max_cloud_cover,
                catalog_id=catalog_id,
            )
            await ctx.info(f'count_eo_scenes -> {result["total_matched"]} matching scene(s)')
            return result
        except ValueError as e:
            await ctx.error(str(e))
            raise ValueError(str(e)) from e

    async def search_eo_scenes(
        self,
        ctx: Context,
        bbox: Annotated[
            list[float],
            Field(description='Bounding box as [min_lon, min_lat, max_lon, max_lat].'),
        ],
        collections: Annotated[
            list[str],
            Field(description='One or more explicit STAC collection ids.'),
        ],
        catalog_id: Annotated[
            str | None,
            Field(description='Registered STAC catalog id. Defaults to earth-search.'),
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
        """Searches Earth observation records inside a bounding box.

        The selected STAC service applies the spatial, temporal, and supported
        provider-specific filters. Results include scene identifiers,
        acquisition times, platforms, cloud cover, native EPSG codes, and
        available asset keys.
        """
        try:

            def _search():
                result = eo.search_scenes(
                    bbox=bbox,
                    collections=collections,
                    datetime_range=datetime_range,
                    max_cloud_cover=max_cloud_cover,
                    limit=limit,
                    catalog_id=catalog_id,
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

    async def create_geocroissant_from_stac(
        self,
        ctx: Context,
        name: Annotated[str, Field(description='Name for the generated dataset.')],
        bbox: Annotated[
            list[float],
            Field(description='Bounding box as [min_lon, min_lat, max_lon, max_lat].'),
        ],
        collections: Annotated[
            list[str], Field(description='One or more explicit STAC collection ids.')
        ],
        catalog_id: Annotated[
            str | None,
            Field(description='Registered STAC catalog id. Defaults to earth-search.'),
        ] = None,
        datetime_range: Annotated[str | None, Field(description='STAC datetime interval.')] = None,
        max_cloud_cover: Annotated[
            float | None, Field(description='Max cloud cover percentage.')
        ] = None,
        limit: Annotated[int, Field(description='Number of scenes to include (1-50).')] = 5,
        description: Annotated[
            str, Field(description='Description of the generated dataset.')
        ] = '',
        license: Annotated[str, Field(description='License URL.')] = '',
        creators: Annotated[list[str] | None, Field(description='Creator names.')] = None,
        spatial_bias: Annotated[
            str,
            Field(description='Description of spatial representativeness limitations (Responsible AI).'),
        ] = '',
        sampling_strategy: Annotated[
            str,
            Field(description='Description of how samples were selected or constructed (Responsible AI).'),
        ] = '',
        data_collection: Annotated[
            str,
            Field(description='Description of the data collection process (Responsible AI).'),
        ] = '',
        data_biases: Annotated[
            list[str] | None,
            Field(description='List of documented imbalances, skews, or historical biases (Responsible AI).'),
        ] = None,
        data_limitations: Annotated[
            list[str] | None,
            Field(description='List of known data generalization limits, quality issues, or non-recommended uses (Responsible AI).'),
        ] = None,
        data_use_cases: Annotated[
            list[str] | None,
            Field(description='Intended, recommended, or benchmark use cases (Responsible AI).'),
        ] = None,
        data_social_impact: Annotated[
            str,
            Field(description='Discussion of positive or negative social impact and risks (Responsible AI).'),
        ] = '',
        personal_sensitive_information: Annotated[
            list[str] | None,
            Field(description='Declarations regarding presence or absence of personal/sensitive information (PII).'),
        ] = None,
        has_synthetic_data: Annotated[
            bool | None,
            Field(description='Whether the dataset contains synthetic data (Responsible AI).'),
        ] = None,
        rai_properties: Annotated[
            dict[str, Any] | None,
            Field(description='Additional Croissant RAI attributes (e.g. data_collection, annotator_demographics, etc.).'),
        ] = None,
        output_filename: Annotated[
            str,
            Field(
                description='When provided, writes the generated JSON-LD into '
                'GEOCR_OUTPUT_DIR (or temp dir) and returns the path.'
            ),
        ] = '',
    ) -> dict[str, Any]:
        """Searches STAC and generates GeoCroissant metadata for matching scenes.

        The document includes spatial and temporal coverage, CRS and band
        metadata, selected provider-native asset URIs, and one inline record per
        scene. The response includes the generated JSON-LD, search summary,
        selected asset URIs, and the result of ``mlcroissant`` metadata
        validation. Validation does not test asset existence or access.
        """

        def _generate():
            search = eo.search_scenes(
                bbox=bbox,
                collections=collections,
                datetime_range=datetime_range,
                max_cloud_cover=max_cloud_cover,
                limit=limit,
                catalog_id=catalog_id,
            )
            raw_items = search.pop('_raw_items')
            doc = eo.geocroissant_from_stac(
                name=name.strip(),
                description=description,
                license_url=license,
                creators=creators or [],
                raw_items=raw_items,
                catalog_id=catalog_id,
                spatial_bias=spatial_bias,
                sampling_strategy=sampling_strategy,
                data_collection=data_collection,
                data_biases=data_biases,
                data_limitations=data_limitations,
                data_use_cases=data_use_cases,
                data_social_impact=data_social_impact,
                personal_sensitive_information=personal_sensitive_information,
                has_synthetic_data=has_synthetic_data,
                rai_properties=rai_properties,
            )
            validation = self._validate_sync(doc)
            path = None
            if output_filename:
                path = str(common.write_json_ld(doc, common.secure_output_path(output_filename)))
            asset_urls = list(map(itemgetter('contentUrl'), doc.get('distribution', [])))
            return {
                **validation,
                'json_ld': doc,
                'path': path,
                'asset_urls': asset_urls,
                'asset_count': len(asset_urls),
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

    async def create_geocroissant_from_stac_sources(
        self,
        ctx: Context,
        name: Annotated[str, Field(description='Name for the generated dataset.')],
        sources: Annotated[
            list[dict[str, Any]],
            Field(
                description='Independent STAC searches. Each object requires catalog_id, '
                'collection_id, and bbox; source_id, datetime_range, max_cloud_cover, and '
                'limit are optional.'
            ),
        ],
        description: Annotated[
            str, Field(description='Description of the generated dataset.')
        ] = '',
        license: Annotated[str, Field(description='License URL for the composed dataset.')] = '',
        creators: Annotated[list[str] | None, Field(description='Creator names.')] = None,
        spatial_bias: Annotated[
            str,
            Field(description='Description of spatial representativeness limitations (Responsible AI).'),
        ] = '',
        sampling_strategy: Annotated[
            str,
            Field(description='Description of how samples were selected or constructed (Responsible AI).'),
        ] = '',
        data_collection: Annotated[
            str,
            Field(description='Description of the data collection process (Responsible AI).'),
        ] = '',
        data_biases: Annotated[
            list[str] | None,
            Field(description='List of documented imbalances, skews, or historical biases (Responsible AI).'),
        ] = None,
        data_limitations: Annotated[
            list[str] | None,
            Field(description='List of known data generalization limits, quality issues, or non-recommended uses (Responsible AI).'),
        ] = None,
        data_use_cases: Annotated[
            list[str] | None,
            Field(description='Intended, recommended, or benchmark use cases (Responsible AI).'),
        ] = None,
        data_social_impact: Annotated[
            str,
            Field(description='Discussion of positive or negative social impact and risks (Responsible AI).'),
        ] = '',
        personal_sensitive_information: Annotated[
            list[str] | None,
            Field(description='Declarations regarding presence or absence of personal/sensitive information (PII).'),
        ] = None,
        has_synthetic_data: Annotated[
            bool | None,
            Field(description='Whether the dataset contains synthetic data (Responsible AI).'),
        ] = None,
        rai_properties: Annotated[
            dict[str, Any] | None,
            Field(description='Additional Croissant RAI attributes (e.g. data_collection, annotator_demographics, etc.).'),
        ] = None,
        output_filename: Annotated[
            str,
            Field(
                description='When provided, writes the generated JSON-LD into '
                'GEOCR_OUTPUT_DIR (or temp dir) and returns the path.'
            ),
        ] = '',
    ) -> dict[str, Any]:
        """Combines any supported catalog and collection searches into one dataset.

        Every source is searched independently, so its filters and limit do not
        affect other sources. The generated GeoCroissant keeps one RecordSet per
        source and does not claim that heterogeneous rasters are aligned or share
        one band configuration. Provider-native asset URIs are preserved.
        """

        def _generate():
            source_results = composition.search_sources(sources)
            document = composition.compose_document(
                name=name.strip(),
                description=description,
                license_url=license,
                creators=creators or [],
                source_results=source_results,
                spatial_bias=spatial_bias,
                sampling_strategy=sampling_strategy,
                data_collection=data_collection,
                data_biases=data_biases,
                data_limitations=data_limitations,
                data_use_cases=data_use_cases,
                data_social_impact=data_social_impact,
                personal_sensitive_information=personal_sensitive_information,
                has_synthetic_data=has_synthetic_data,
                rai_properties=rai_properties,
            )
            validation = self._validate_sync(document)
            path = None
            if output_filename:
                path = str(
                    common.write_json_ld(
                        document,
                        common.secure_output_path(output_filename),
                    )
                )
            assets = composition.asset_manifest(source_results)
            source_summaries = [
                {
                    'source_id': result['source_id'],
                    'catalog_id': result['catalog_id'],
                    'collection_id': result['collection_id'],
                    'bbox': result['search']['bbox'],
                    'datetime_range': result['search']['datetime_range'],
                    'max_cloud_cover': result['search']['max_cloud_cover'],
                    'requested_limit': result['limit'],
                    'scene_count': result['search']['scene_count'],
                    'notes': result['search']['notes'],
                }
                for result in source_results
            ]
            asset_urls = list(map(itemgetter('contentUrl'), document.get('distribution', [])))
            return {
                **validation,
                'json_ld': document,
                'path': path,
                'asset_urls': asset_urls,
                'asset_count': len(asset_urls),
                'assets': assets,
                'source_results': source_summaries,
                'scene_count': sum(result['scene_count'] for result in source_summaries),
            }

        try:
            result = await asyncio.to_thread(_generate)
            status = 'passed' if result['valid'] else 'FAILED'
            await ctx.info(
                f'GeoCroissant `{name}` from {len(result["source_results"])} source(s) '
                f'and {result["scene_count"]} scene(s): validation {status}'
            )
            return result
        except ValueError as e:
            logger.warning(f'Cannot compose GeoCroissant from STAC sources: {e}')
            await ctx.error(str(e))
            raise ValueError(str(e)) from e

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

        Runs the configured ``mlcroissant`` validator: JSON syntax checks,
        JSON-LD expansion, structure-graph construction (FileObjects/FileSets,
        RecordSets, Fields, sources, and joins), and schema conformance checks.
        It does not verify remote asset availability or authorization.
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
        return await asyncio.to_thread(self._validate_sync, source_arg)

    def _validate_sync(self, source: dict[str, Any] | str) -> dict[str, Any]:
        """Runs mlcroissant static analysis synchronously."""
        from mlcroissant import ValidationError

        source_desc = 'inline JSON content' if isinstance(source, dict) else source
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

        Parses the document with ``mlcroissant`` and summarizes core metadata,
        GeoCroissant properties, distribution entries, RecordSets, Fields, array
        shapes, and source, extraction, and transformation chains.
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

        Nodes represent Metadata, FileObject, FileSet, RecordSet, and Field
        objects. Directed edges represent containment, source, and reference
        relationships in the graph built by ``mlcroissant``.
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

        Each summary includes the RecordSet identifier, key fields, inline data
        count, and nested Field types and source chains. Pass a returned
        identifier to `get_records_preview`.
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

        Uses ``Dataset.records(record_set)`` to resolve local or remote
        distributions and apply declared extraction and transformation steps.
        Remote sources may require downloads and credentials. Inline `cr:data`
        records do not require distribution access. ``truncated`` is true when
        the preview reaches the requested limit; more records may exist.
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
        """Extracts source asset URIs from a Croissant document's distribution.

        Collects the `contentUrl` of every FileObject together with its encoding
        formats, sizes and checksums, plus FileSet include patterns and archive
        containers. Access may require credentials appropriate for each URI scheme.

                Returns one summary per distribution entry, including names, types,
                source URIs, formats, checksums, include patterns, and container
                references when declared. Access depends on the source provider.
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
            urls = common.summarize_distribution(dataset.metadata)
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
        spatial_bias: Annotated[
            str,
            Field(description='Description of spatial representativeness limitations (Responsible AI).'),
        ] = '',
        sampling_strategy: Annotated[
            str,
            Field(description='Description of how samples were selected or constructed (Responsible AI).'),
        ] = '',
        data_biases: Annotated[
            list[str] | None,
            Field(description='List of documented imbalances, skews, or historical biases (Responsible AI).'),
        ] = None,
        data_limitations: Annotated[
            list[str] | None,
            Field(description='List of known data generalization limits, quality issues, or non-recommended uses (Responsible AI).'),
        ] = None,
        data_use_cases: Annotated[
            list[str] | None,
            Field(description='Intended, recommended, or benchmark use cases (Responsible AI).'),
        ] = None,
        data_social_impact: Annotated[
            str,
            Field(description='Discussion of positive or negative social impact and risks (Responsible AI).'),
        ] = '',
        personal_sensitive_information: Annotated[
            list[str] | None,
            Field(description='Declarations regarding presence or absence of personal/sensitive information (PII).'),
        ] = None,
        has_synthetic_data: Annotated[
            bool | None,
            Field(description='Whether the dataset contains synthetic data (Responsible AI).'),
        ] = None,
        rai_properties: Annotated[
            dict[str, Any] | None,
            Field(description='Additional Croissant RAI attributes (e.g. data_collection, annotator_demographics, etc.).'),
        ] = None,
        output_filename: Annotated[
            str,
            Field(
                description=(
                    'When provided, writes the generated JSON-LD to this filename '
                    'inside GEOCR_OUTPUT_DIR (or the system temp dir) and returns '
                    'the path.'
                )
            ),
        ] = '',
    ) -> ScaffoldResult:
        """Generates a GeoCroissant JSON-LD scaffold from parameters.

        Produces a starting point based on the GeoCroissant example: an @context
        containing the `geocr` prefix,
        dual conformance (`croissant/1.1` + `geocr`), schema.org spatial/temporal
        coverage, GeoCroissant properties (CRS, resolutions, band configuration,
        spectral bands), distribution entries and a RecordSet wired to them via
        cr:source and cr:extract declarations.

        The response includes the generated document and its ``mlcroissant``
        metadata validation result. Edit domain-specific values and validate the
        document again before publication.
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
                spatial_bias=spatial_bias,
                sampling_strategy=sampling_strategy,
                data_biases=data_biases,
                data_limitations=data_limitations,
                data_use_cases=data_use_cases,
                data_social_impact=data_social_impact,
                personal_sensitive_information=personal_sensitive_information,
                has_synthetic_data=has_synthetic_data,
                rai_properties=rai_properties,
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

        result = await asyncio.to_thread(_finalize)
        level = 'passed' if result.valid else 'FAILED'
        await ctx.info(
            f'Scaffold `{name}` validation {level}' + (f'; written to {path}' if path else '')
        )
        return result

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
                    'properties), "rai" (Responsible AI properties catalog), '
                    '"example" (sample document), '
                    '"python-api" (mlcroissant usage snippets), "all" (all topics).'
                )
            ),
        ] = 'all',
    ) -> str:
        """Returns the GeoCroissant specification reference documentation.

        Returns namespace IRIs, conformance declarations, GeoCroissant property
        types and cardinalities, the JSON-LD context used by the server, a
        condensed example, and ``mlcroissant`` usage notes.
        """
        del ctx  # No side effects; kept for FastMCP signature consistency.
        topic_normalized = (topic or 'all').strip().lower()
        if topic_normalized not in reference.TOPICS:
            raise ValueError(
                f'Unknown topic "{topic}". Choose one of: {sorted(reference.TOPICS)}.'
            )
        return reference.render_reference(topic_normalized)
