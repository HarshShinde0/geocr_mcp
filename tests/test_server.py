"""Unit tests for server wiring and response models."""

from geocr_mcp_server.models import ValidationReport
from geocr_mcp_server.server import mcp
from unittest.mock import AsyncMock


EXPECTED_TOOLS = {
    'list_eo_catalogs',
    'search_eo_datasets',
    'search_eo_scenes',
    'validate_croissant',
    'inspect_geocroissant',
    'get_structure_graph',
    'list_record_sets',
    'get_records_preview',
    'extract_distribution_urls',
    'create_geocroissant_scaffold',
    'create_geocroissant_from_stac',
    'get_geocroissant_spec_reference',
}


def test_all_tools_registered():
    """Every expected tool is registered on the FastMCP instance."""
    registered = set(mcp._tool_manager._tools.keys())
    assert EXPECTED_TOOLS == registered


def test_server_name():
    assert mcp.name == 'geocr-mcp-server'


def test_server_has_instructions():
    instructions = mcp.instructions or ''
    assert 'GeoCroissant' in instructions
    assert 'validate_croissant' in instructions


class TestValidationReportModel:
    def test_exclude_none_default(self):
        report = ValidationReport(valid=True)
        dump = report.model_dump()
        assert 'source' not in dump
        assert dump['is_geospatial'] is False

    async def test_report_usable_from_tool(self):
        """ValidationReport round-trips through model_validate."""
        report = ValidationReport.model_validate({'valid': False, 'errors': ['boom']})
        ctx = AsyncMock()
        del ctx  # unused; mirrors tool error paths
        assert report.valid is False
        assert report.errors == ['boom']
