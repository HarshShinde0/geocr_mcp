"""Public tool tests executed through the MCP protocol."""

import json
import pystac
import pytest
from geocr_mcp_server import eo
from geocr_mcp_server.server import mcp
from mcp.shared.memory import create_connected_server_and_client_session
from pathlib import Path
from tests.test_eo import _stac_item, _veda_stac_item


async def _call(name: str, arguments: dict):
    async with create_connected_server_and_client_session(mcp) as session:
        return await session.call_tool(name, arguments)


def _structured(result):
    assert result.isError is False, result.content
    assert result.structuredContent is not None
    return result.structuredContent


class TestValidateCroissant:
    async def test_valid_file(self, valid_geocroissant_file):
        report = _structured(
            await _call('validate_croissant', {'jsonld_path': valid_geocroissant_file})
        )
        assert report['valid'] is True
        assert report['errors'] == []
        assert report['is_geospatial'] is True
        assert any('croissant/1.1' in value for value in report['conforms_to'])
        assert report['dataset_name'] == 'Test Burn Scars'

    async def test_valid_inline(self, valid_geocroissant):
        report = _structured(
            await _call(
                'validate_croissant',
                {'jsonld_content': json.dumps(valid_geocroissant)},
            )
        )
        assert report['valid'] is True

    @pytest.mark.parametrize(
        'fixture_name',
        ['invalid_geocroissant_content', 'malformed_json_content'],
    )
    async def test_invalid_documents_report_errors(self, fixture_name, request):
        content = request.getfixturevalue(fixture_name)
        report = _structured(
            await _call('validate_croissant', {'jsonld_content': content})
        )
        assert report['valid'] is False
        assert report['errors']

    async def test_missing_and_multiple_inputs_are_tool_errors(self, tmp_path):
        missing = await _call('validate_croissant', {})
        assert missing.isError is True

        path = tmp_path / 'metadata.json'
        path.write_text('{}', encoding='utf-8')
        multiple = await _call(
            'validate_croissant',
            {'jsonld_path': str(path), 'jsonld_url': 'https://example.com/metadata.json'},
        )
        assert multiple.isError is True

    async def test_malformed_context_reports_runtime_error(self):
        report = _structured(
            await _call(
                'validate_croissant',
                {
                    'jsonld_content': json.dumps(
                        {'@context': 3, '@type': 'Dataset', 'name': 'Invalid context'}
                    )
                },
            )
        )
        assert report['valid'] is False
        assert report['errors']


class TestInspection:
    async def test_full_summary(self, valid_geocroissant_file):
        summary = _structured(
            await _call('inspect_geocroissant', {'jsonld_path': valid_geocroissant_file})
        )
        assert summary['name'] == 'Test Burn Scars'
        assert summary['geospatial']['coordinateReferenceSystem'] == 'EPSG:4326'
        assert summary['geospatial']['bandConfiguration']['totalBands'] == 6
        assert summary['distribution'][0]['includes'] == ['images/**/*.tif']
        record_sets = {record_set['@id']: record_set for record_set in summary['record_sets']}
        assert set(record_sets) == {'images_recordset', 'labels'}
        assert record_sets['images_recordset']['fields'][0]['arrayShape'] == '512,512,6'

    async def test_structure_graph(self, valid_geocroissant_file):
        graph = _structured(
            await _call('get_structure_graph', {'jsonld_path': valid_geocroissant_file})
        )
        assert {node['type'] for node in graph['nodes']} == {
            'Metadata',
            'FileSet',
            'RecordSet',
            'Field',
        }
        assert graph['edge_count'] == len(graph['edges'])
        assert graph['node_count'] == len(graph['nodes'])
        assert any(
            edge['source'] == 'images' and edge['target'].startswith('images_recordset')
            for edge in graph['edges']
        )

    async def test_record_sets_and_preview(self, valid_geocroissant_file):
        arguments = {'jsonld_path': valid_geocroissant_file}
        record_sets = _structured(await _call('list_record_sets', arguments))['result']
        by_id = {record_set['@id']: record_set for record_set in record_sets}
        assert by_id['labels']['field_count'] == 3
        assert by_id['labels']['num_declared_records'] == 3

        preview = _structured(
            await _call(
                'get_records_preview',
                {**arguments, 'record_set': 'labels', 'limit': 2},
            )
        )
        assert preview['num_records'] == 2
        assert preview['truncated'] is True
        assert preview['rows'][0]['labels/region'] == 'north'

        unknown = await _call(
            'get_records_preview',
            {**arguments, 'record_set': 'does-not-exist'},
        )
        assert unknown.isError is True

    async def test_distribution_urls(self, valid_geocroissant_file):
        urls = _structured(
            await _call(
                'extract_distribution_urls',
                {'jsonld_path': valid_geocroissant_file},
            )
        )
        assert urls['count'] == 1
        assert urls['urls'][0]['includes'] == ['images/**/*.tif']

    async def test_complete_records_and_empty_distributions(self, valid_geocroissant):
        preview = _structured(
            await _call(
                'get_records_preview',
                {
                    'record_set': 'labels',
                    'limit': 100,
                    'jsonld_content': json.dumps(valid_geocroissant),
                },
            )
        )
        assert preview['num_records'] == 3
        assert preview['truncated'] is False

        document = json.loads(json.dumps(valid_geocroissant))
        document['distribution'] = []
        document['recordSet'] = [document['recordSet'][1]]
        urls = _structured(
            await _call(
                'extract_distribution_urls',
                {'jsonld_content': json.dumps(document)},
            )
        )
        assert urls == {'urls': [], 'count': 0}

    @pytest.mark.parametrize(
        'tool_name,arguments',
        [
            ('inspect_geocroissant', {}),
            ('get_structure_graph', {}),
            ('list_record_sets', {}),
            ('get_records_preview', {'record_set': 'records'}),
            ('extract_distribution_urls', {}),
        ],
    )
    async def test_missing_document_is_tool_error(self, tool_name, arguments):
        result = await _call(tool_name, arguments)
        assert result.isError is True

    @pytest.mark.parametrize(
        'tool_name,arguments',
        [
            ('inspect_geocroissant', {'jsonld_content': '{}'}),
            ('get_structure_graph', {'jsonld_content': '{}'}),
            ('list_record_sets', {'jsonld_content': '{}'}),
            (
                'get_records_preview',
                {'record_set': 'records', 'jsonld_content': '{}'},
            ),
            ('extract_distribution_urls', {'jsonld_content': '{}'}),
        ],
    )
    async def test_invalid_document_is_tool_error(self, tool_name, arguments):
        result = await _call(tool_name, arguments)
        assert result.isError is True


class TestEoInputErrors:
    @pytest.mark.parametrize(
        'tool_name,arguments',
        [
            ('search_eo_datasets', {'catalog_id': '__unregistered__'}),
            ('get_eo_dataset_details', {'collection_id': ' '}),
            ('geocode_place', {'place_name': ' '}),
            ('count_eo_scenes', {'bbox': [0, 0], 'collections': ['collection']}),
            ('search_eo_scenes', {'bbox': [0, 0], 'collections': ['collection']}),
            (
                'create_geocroissant_from_stac',
                {'name': 'Dataset', 'bbox': [0, 0], 'collections': ['collection']},
            ),
            ('create_geocroissant_from_stac_sources', {'name': 'Dataset', 'sources': []}),
        ],
    )
    async def test_invalid_input_is_tool_error(self, tool_name, arguments):
        result = await _call(tool_name, arguments)
        assert result.isError is True


class TestStacComposition:
    async def test_combines_sources_through_protocol(self, monkeypatch, tmp_path):
        class Search:
            def __init__(self, item):
                self.item = item

            def items(self):
                return [pystac.Item.from_dict(self.item)]

        class Client:
            def search(self, **kwargs):
                collection_id = kwargs['collections'][0]
                if collection_id == 'sentinel-2-c1-l2a':
                    return Search(_stac_item())
                return Search(_veda_stac_item())

        monkeypatch.setattr(eo, '_open_client', lambda url: Client())
        monkeypatch.setenv('GEOCR_OUTPUT_DIR', str(tmp_path))

        result = _structured(
            await _call(
                'create_geocroissant_from_stac_sources',
                {
                    'name': 'Combined observations',
                    'sources': [
                        {
                            'catalog_id': 'earth-search',
                            'collection_id': 'sentinel-2-c1-l2a',
                            'bbox': [-53, -31, -50, -28],
                            'limit': 2,
                            'datetime_range': '2026-08-01/2026-08-25',
                            'max_cloud_cover': 20,
                        },
                        {
                            'catalog_id': 'veda',
                            'collection_id': 'no2-monthly',
                            'bbox': [-180, -90, 180, 90],
                        }
                    ],
                    'output_filename': 'composed.json',
                },
            )
        )

        assert result['valid'] is True, result['errors']
        assert result['scene_count'] == 2
        assert result['asset_count'] == len(result['asset_urls'])
        assert Path(result['path']).is_file()
        assert {source['catalog_id'] for source in result['source_results']} == {
            'earth-search',
            'veda',
        }
        assert any(asset['href'].startswith('s3://') for asset in result['assets'])


class TestScaffold:
    async def test_generates_valid_scaffold(self):
        result = _structured(
            await _call(
                'create_geocroissant_scaffold',
                {
                    'name': 'My EO Dataset',
                    'description': 'Protocol test scaffold.',
                    'license': 'https://creativecommons.org/licenses/by/4.0/',
                    'version': '1.0',
                    'bbox': [-125.0, 24.0, -66.0, 49.0],
                    'temporal_coverage': '2018-01-01/2021-12-31',
                    'coordinate_reference_system': 'EPSG:4326',
                    'spatial_resolution': 30,
                    'band_names': ['Blue', 'Green', 'Red', 'NIR'],
                    'spectral_bands': [
                        {
                            'name': 'Blue',
                            'centerWavelengthValue': 490,
                            'centerWavelengthUnit': 'nm',
                        }
                    ],
                    'file_sets': [
                        {
                            'id': 'images',
                            'name': 'Images',
                            'encoding_format': 'image/tiff',
                            'includes': 'images/**/*.tif',
                        }
                    ],
                    'field_is_array': True,
                    'field_array_shape': '512,512,4',
                },
            )
        )
        assert result['valid'] is True, result['errors']
        document = result['json_ld']
        assert document['spatialCoverage']['geo']['box'] == '24.0 -125.0 49.0 -66.0'
        assert document['recordSet'][0]['field'][0]['source']['fileSet']['@id'] == 'images'

    async def test_writes_output_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv('GEOCR_OUTPUT_DIR', str(tmp_path))
        result = _structured(
            await _call(
                'create_geocroissant_scaffold',
                {'name': 'Written Dataset', 'output_filename': 'out.json'},
            )
        )
        assert result['path'] is not None
        written = json.loads(Path(result['path']).read_text(encoding='utf-8'))
        assert written['name'] == 'Written Dataset'

    @pytest.mark.parametrize(
        'arguments',
        [
            {'name': 'X', 'field_array_shape': '10,10'},
            {'name': ' '},
            {'name': 'X', 'file_objects': [{'id': 'f1'}]},
        ],
    )
    async def test_invalid_scaffold_arguments_are_tool_errors(self, arguments):
        result = await _call('create_geocroissant_scaffold', arguments)
        assert result.isError is True


class TestSpecReference:
    async def test_all_sections(self):
        text = _structured(
            await _call('get_geocroissant_spec_reference', {'topic': 'all'})
        )['result']
        for section in ('Server @context', 'Properties Reference', 'Python API'):
            assert section in text

    @pytest.mark.parametrize('topic', ['overview', 'context', 'properties', 'example'])
    async def test_single_topic(self, topic):
        text = _structured(
            await _call('get_geocroissant_spec_reference', {'topic': topic})
        )['result']
        assert '# ' in text

    async def test_unknown_topic_is_tool_error(self):
        result = await _call('get_geocroissant_spec_reference', {'topic': 'invalid'})
        assert result.isError is True
