"""Integration tests that exercise tools through the MCP protocol."""

import json
from geocr_mcp_server.server import mcp
from mcp.shared.memory import create_connected_server_and_client_session


async def test_protocol_lists_public_tools_and_input_schemas():
    async with create_connected_server_and_client_session(mcp) as session:
        tools = {tool.name: tool for tool in (await session.list_tools()).tools}

    assert set(tools) == set(mcp._tool_manager._tools)
    discovery_inputs = set(tools['search_eo_datasets'].inputSchema['properties'])
    assert discovery_inputs == {'catalog_id', 'limit', 'offset'}
    assert {'keyword', 'topic', 'modality', 'query'}.isdisjoint(discovery_inputs)
    composition_inputs = set(
        tools['create_geocroissant_from_stac_sources'].inputSchema['properties']
    )
    assert composition_inputs == {
        'name',
        'sources',
        'description',
        'license',
        'creators',
        'spatial_bias',
        'sampling_strategy',
        'data_collection',
        'data_biases',
        'data_limitations',
        'data_use_cases',
        'data_social_impact',
        'personal_sensitive_information',
        'has_synthetic_data',
        'rai_properties',
        'output_filename',
    }


async def test_protocol_ping_returns_pong():
    async with create_connected_server_and_client_session(mcp) as session:
        tools = {tool.name: tool for tool in (await session.list_tools()).tools}
        result = await session.call_tool('ping', {})

    assert tools['ping'].inputSchema['properties'] == {}
    assert result.isError is False
    assert result.content[0].text == 'pong'


async def test_protocol_scaffold_validation_round_trip():
    async with create_connected_server_and_client_session(mcp) as session:
        generated = await session.call_tool(
            'create_geocroissant_scaffold',
            {
                'name': 'Maharashtra Flood Analysis',
                'description': 'Protocol integration test dataset.',
                'bbox': [72.6, 15.6, 80.9, 22.1],
                'temporal_coverage': '2020-01-01/2025-12-31',
                'coordinate_reference_system': 'EPSG:4326',
            },
        )
        assert generated.isError is False
        assert generated.structuredContent is not None
        assert generated.structuredContent['valid'] is True

        validated = await session.call_tool(
            'validate_croissant',
            {'jsonld_content': json.dumps(generated.structuredContent['json_ld'])},
        )

    assert validated.isError is False
    assert validated.structuredContent is not None
    assert validated.structuredContent['valid'] is True
    assert validated.structuredContent['dataset_name'] == 'Maharashtra Flood Analysis'


async def test_protocol_returns_tool_error_for_invalid_bbox():
    async with create_connected_server_and_client_session(mcp) as session:
        result = await session.call_tool(
            'search_eo_scenes',
            {'bbox': [72.6, 15.6], 'collections': ['sentinel-2-c1-l2a']},
        )

    assert result.isError is True
    assert result.content
