"""Live external-service and end-to-end MCP contracts."""

import json
import pytest
from geocr_mcp_server import catalogs
from geocr_mcp_server.server import mcp
from mcp.shared.memory import create_connected_server_and_client_session
from pathlib import Path


pytestmark = pytest.mark.live
CATALOG_IDS = tuple(catalogs.get_config()['catalogs'])


async def _call(session, name, arguments):
    result = await session.call_tool(name, arguments)
    assert result.isError is False, result.content
    assert result.structuredContent is not None
    return result.structuredContent


async def test_live_catalog_registry_and_geocoding_through_mcp():
    async with create_connected_server_and_client_session(mcp) as session:
        listed = await _call(session, 'list_eo_catalogs', {})
        assert {catalog['id'] for catalog in listed['catalogs']} == set(CATALOG_IDS)

        location = await _call(
            session,
            'geocode_place',
            {'place_name': 'Maharashtra, India', 'limit': 3},
        )

    assert location['count'] >= 1
    west, south, east, north = location['candidates'][0]['bbox']
    assert -180 <= west < east <= 180
    assert -90 <= south < north <= 90


async def test_live_generation_without_output_file():
    catalog_id = CATALOG_IDS[0]
    async with create_connected_server_and_client_session(mcp) as session:
        page = await _call(
            session,
            'search_eo_datasets',
            {'catalog_id': catalog_id, 'limit': 1},
        )
        collection_id = page['collections'][0]['collection']
        details = await _call(
            session,
            'get_eo_dataset_details',
            {'catalog_id': catalog_id, 'collection_id': collection_id},
        )
        generated = await _call(
            session,
            'create_geocroissant_from_stac',
            {
                'catalog_id': catalog_id,
                'collections': [collection_id],
                'bbox': details['collection']['extent']['spatial']['bbox'][0][:4],
                'limit': 1,
                'name': 'Live in-memory dataset',
            },
        )

    assert generated['valid'] is True
    assert generated['path'] is None


async def test_live_composition_uses_registered_catalogs_and_repeated_catalog():
    sources = []
    async with create_connected_server_and_client_session(mcp) as session:
        for catalog_id in CATALOG_IDS:
            page = await _call(
                session,
                'search_eo_datasets',
                {'catalog_id': catalog_id, 'limit': 1},
            )
            collection_id = page['collections'][0]['collection']
            details = await _call(
                session,
                'get_eo_dataset_details',
                {'catalog_id': catalog_id, 'collection_id': collection_id},
            )
            sources.append(
                {
                    'catalog_id': catalog_id,
                    'collection_id': collection_id,
                    'bbox': details['collection']['extent']['spatial']['bbox'][0][:4],
                    'limit': 1,
                }
            )

        sources.append({**sources[0], 'source_id': 'same-catalog-second-source'})
        generated = await _call(
            session,
            'create_geocroissant_from_stac_sources',
            {'name': 'Live composed dataset', 'sources': sources},
        )

    assert generated['valid'] is True
    assert generated['scene_count'] == len(sources)
    assert len(generated['source_results']) == len(sources)
    assert generated['source_results'][0]['catalog_id'] == generated['source_results'][-1][
        'catalog_id'
    ]
    assert len(generated['json_ld']['recordSet']) == len(sources)


@pytest.mark.parametrize('catalog_id', CATALOG_IDS)
async def test_live_catalog_to_validated_dataset_through_mcp(
    catalog_id, monkeypatch, tmp_path
):
    monkeypatch.setenv('GEOCR_OUTPUT_DIR', str(tmp_path))
    async with create_connected_server_and_client_session(mcp) as session:
        page = await _call(
            session,
            'search_eo_datasets',
            {'catalog_id': catalog_id, 'limit': 1, 'offset': 0},
        )
        assert page['count'] == 1
        assert page['total_catalog_collections'] >= page['count']

        collection_id = page['collections'][0]['collection']
        details = await _call(
            session,
            'get_eo_dataset_details',
            {'catalog_id': catalog_id, 'collection_id': collection_id},
        )
        assert details['collection']['id'] == collection_id

        bbox = details['collection']['extent']['spatial']['bbox'][0][:4]
        search = {
            'catalog_id': catalog_id,
            'collections': [collection_id],
            'bbox': bbox,
        }
        counts = await _call(session, 'count_eo_scenes', search)
        assert counts['counts'][collection_id] > 0

        scenes = await _call(session, 'search_eo_scenes', {**search, 'limit': 1})
        assert scenes['scene_count'] == 1
        assert scenes['scenes'][0]['asset_keys']

        generated = await _call(
            session,
            'create_geocroissant_from_stac',
            {
                **search,
                'limit': 1,
                'name': f'Live MCP {catalog_id} Dataset',
                'output_filename': f'{catalog_id}.json',
            },
        )
        assert generated['valid'] is True
        assert generated['asset_count'] == len(generated['asset_urls']) > 0
        assert Path(generated['path']).is_file()

        document = json.dumps(generated['json_ld'])
        validated = await _call(session, 'validate_croissant', {'jsonld_content': document})
        urls = await _call(session, 'extract_distribution_urls', {'jsonld_content': document})

    assert validated['valid'] is True
    assert urls['count'] == generated['asset_count']
