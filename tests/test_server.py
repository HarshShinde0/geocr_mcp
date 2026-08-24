"""Unit tests for server wiring and response models."""

import httpx
import importlib
import sys
from geocr_mcp_server import server
from geocr_mcp_server.models import ValidationReport
from geocr_mcp_server.server import mcp


EXPECTED_TOOLS = {
    'ping',
    'list_eo_catalogs',
    'search_eo_datasets',
    'get_eo_dataset_details',
    'geocode_place',
    'count_eo_scenes',
    'search_eo_scenes',
    'validate_croissant',
    'inspect_geocroissant',
    'get_structure_graph',
    'list_record_sets',
    'get_records_preview',
    'extract_distribution_urls',
    'create_geocroissant_scaffold',
    'create_geocroissant_from_stac',
    'create_geocroissant_from_stac_sources',
    'get_geocroissant_spec_reference',
}


def test_all_tools_registered():
    """Every expected tool is registered on the FastMCP instance."""
    registered = set(mcp._tool_manager._tools.keys())
    assert EXPECTED_TOOLS == registered


def test_eo_tools_do_not_expose_intent_classification_parameters():
    forbidden = {'keyword', 'keywords', 'topic', 'topics', 'modality', 'modalities', 'query'}

    for tool_name in (
        'search_eo_datasets',
        'search_eo_scenes',
        'create_geocroissant_from_stac',
        'create_geocroissant_from_stac_sources',
    ):
        properties = mcp._tool_manager._tools[tool_name].parameters.get('properties', {})
        assert forbidden.isdisjoint(properties)


def test_server_name():
    assert mcp.name == 'geocr-mcp-server'


def test_server_has_instructions():
    instructions = mcp.instructions or ''
    assert 'GeoCroissant' in instructions
    assert 'validate_croissant' in instructions


async def test_health_route_through_asgi():
    transport = httpx.ASGITransport(app=mcp.streamable_http_app())
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.get('/')
        head = await client.head('/')

    assert response.status_code == 200
    assert response.json()['status'] == 'online'
    assert response.json()['version']
    assert head.status_code == 200


def test_main_applies_explicit_local_settings(monkeypatch):
    invocation = {}
    monkeypatch.setattr(sys, 'argv', ['geocr-mcp-server', '--transport', 'stdio', '--port', '8123'])
    monkeypatch.setattr(mcp, 'run', lambda **kwargs: invocation.update(kwargs))

    server.main()

    assert mcp.settings.host == '127.0.0.1'
    assert mcp.settings.port == 8123
    assert invocation == {'transport': 'stdio'}


def test_cloud_defaults_and_transport_security(monkeypatch):
    monkeypatch.setenv('PORT', '8124')
    cloud_server = importlib.reload(server)
    invocation = {}
    monkeypatch.setattr(sys, 'argv', ['geocr-mcp-server'])
    monkeypatch.setattr(cloud_server.mcp, 'run', lambda **kwargs: invocation.update(kwargs))

    cloud_server.main()

    assert cloud_server.mcp.settings.host == '0.0.0.0'
    assert cloud_server.mcp.settings.port == 8124
    assert cloud_server.mcp.settings.transport_security.allowed_hosts == ['*']
    assert invocation == {'transport': 'streamable-http'}


class TestValidationReportModel:
    def test_exclude_none_default(self):
        report = ValidationReport(valid=True)
        dump = report.model_dump()
        assert 'source' not in dump
        assert dump['is_geospatial'] is False
