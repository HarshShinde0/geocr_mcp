"""Unit tests for the MCP tools (no network access required)."""

import json
import pytest
from geocr_mcp_server.models import (
    DistributionUrls,
    RecordsPreview,
    ScaffoldResult,
    StructureGraph,
)
from geocr_mcp_server.tools import GeoCroissantTools
from unittest.mock import AsyncMock


@pytest.fixture
def tools() -> GeoCroissantTools:
    return GeoCroissantTools()


@pytest.fixture
def ctx() -> AsyncMock:
    return AsyncMock()


class TestValidateCroissant:
    async def test_valid_file(self, tools, ctx, valid_geocroissant_file):
        report = await tools.validate_croissant(ctx, jsonld_path=valid_geocroissant_file)
        assert isinstance(report, dict)
        assert report['valid'] is True
        assert report['errors'] == []
        assert report['is_geospatial'] is True
        assert any('croissant/1.1' in c for c in report['conforms_to'])
        assert report['dataset_name'] == 'Test Burn Scars'

    async def test_valid_inline(self, tools, ctx, valid_geocroissant):
        report = await tools.validate_croissant(ctx, jsonld_content=json.dumps(valid_geocroissant))
        assert report['valid'] is True

    async def test_invalid_document_reports_errors(self, tools, ctx, invalid_geocroissant_content):
        report = await tools.validate_croissant(ctx, jsonld_content=invalid_geocroissant_content)
        assert report['valid'] is False
        assert len(report['errors']) > 0

    async def test_malformed_json_reports_errors(self, tools, ctx, malformed_json_content):
        report = await tools.validate_croissant(ctx, jsonld_content=malformed_json_content)
        assert report['valid'] is False

    async def test_missing_input_raises(self, tools, ctx):
        with pytest.raises(ValueError, match='No input'):
            await tools.validate_croissant(ctx)

    async def test_multiple_inputs_raise(self, tools, ctx, tmp_path):
        f = tmp_path / 'm.json'
        f.write_text('{}')
        with pytest.raises(ValueError, match='Multiple inputs'):
            await tools.validate_croissant(ctx, jsonld_path=str(f), jsonld_url='https://x')


class TestInspectGeocroissant:
    async def test_full_summary(self, tools, ctx, valid_geocroissant_file):
        summary = await tools.inspect_geocroissant(ctx, jsonld_path=valid_geocroissant_file)
        assert summary['name'] == 'Test Burn Scars'
        geo = summary['geospatial']
        assert geo['coordinateReferenceSystem'] == 'EPSG:4326'
        assert geo['spatialResolution']['value'] == 30
        assert geo['bandConfiguration']['totalBands'] == 6
        assert geo['bandConfiguration']['bandNamesList'][0] == 'Blue'
        assert geo['spectralBandMetadata'][0]['centerWavelength']['value'] == 490
        dist = summary['distribution']
        assert dist[0]['@id'] == 'images'
        assert dist[0]['includes'] == ['images/**/*.tif']
        record_sets = {rs['@id']: rs for rs in summary['record_sets']}
        assert set(record_sets) == {'images_recordset', 'labels'}
        image_field = record_sets['images_recordset']['fields'][0]
        assert image_field['isArray'] is True
        assert image_field['arrayShape'] == '512,512,6'
        assert image_field['source']['fileSet']['@id'] == 'images'

    async def test_invalid_document_raises(self, tools, ctx, malformed_json_content):
        with pytest.raises(Exception):
            await tools.inspect_geocroissant(ctx, jsonld_content=malformed_json_content)


class TestGetStructureGraph:
    async def test_nodes_and_edges(self, tools, ctx, valid_geocroissant_file):
        graph = await tools.get_structure_graph(ctx, jsonld_path=valid_geocroissant_file)
        assert isinstance(graph, StructureGraph)
        types = {n['type'] for n in graph.nodes}
        assert types == {'Metadata', 'FileSet', 'RecordSet', 'Field'}
        assert graph.edge_count == len(graph.edges)
        assert graph.node_count == len(graph.nodes)
        ids = {n['@id'] for n in graph.nodes}
        assert 'images_recordset/image' in ids
        # FileSet -> RecordSet edge (source feeding the record set).
        assert any(
            e['source'] == 'images' and e['target'].startswith('images_recordset')
            for e in graph.edges
        )

    async def test_dump_excludes_none(self, tools, ctx, valid_geocroissant_file):
        graph = await tools.get_structure_graph(ctx, jsonld_path=valid_geocroissant_file)
        dump = graph.model_dump()
        assert '@id' in dump['nodes'][0]


class TestListRecordSets:
    async def test_lists_both_record_sets(self, tools, ctx, valid_geocroissant_file):
        record_sets = await tools.list_record_sets(ctx, jsonld_path=valid_geocroissant_file)
        by_id = {rs['@id']: rs for rs in record_sets}
        assert by_id['labels']['field_count'] == 3
        assert by_id['labels']['num_declared_records'] == 3
        assert by_id['images_recordset']['fields'][0]['dataType'] == [
            'https://schema.org/ImageObject'
        ]


class TestGetRecordsPreview:
    async def test_reads_inline_data(self, tools, ctx, valid_geocroissant_file):
        preview = await tools.get_records_preview(
            ctx, record_set='labels', limit=2, jsonld_path=valid_geocroissant_file
        )
        assert isinstance(preview, RecordsPreview)
        assert preview.num_records == 2
        assert preview.truncated is True
        assert 'labels/id' in preview.columns
        assert preview.rows[0]['labels/region'] == 'north'

    async def test_unknown_record_set_raises(self, tools, ctx, valid_geocroissant_file):
        with pytest.raises(ValueError, match='record set'):
            await tools.get_records_preview(
                ctx, record_set='nope', jsonld_path=valid_geocroissant_file
            )


class TestExtractDistributionUrls:
    async def test_finds_fileset_includes(self, tools, ctx, valid_geocroissant_file):
        urls = await tools.extract_distribution_urls(ctx, jsonld_path=valid_geocroissant_file)
        assert isinstance(urls, DistributionUrls)
        assert urls.count == 1
        assert urls.urls[0]['includes'] == ['images/**/*.tif']


class TestCreateGeocroissantScaffold:
    async def test_generates_valid_scaffold(self, tools, ctx):
        result = await tools.create_geocroissant_scaffold(
            ctx,
            name='My EO Dataset',
            description='A test scaffold.',
            license='https://creativecommons.org/licenses/by/4.0/',
            version='1.0',
            bbox=[-125.0, 24.0, -66.0, 49.0],
            temporal_coverage='2018-01-01/2021-12-31',
            coordinate_reference_system='EPSG:4326',
            spatial_resolution=30,
            band_names=['Blue', 'Green', 'Red', 'NIR'],
            spectral_bands=[
                {'name': 'Blue', 'centerWavelengthValue': 490, 'centerWavelengthUnit': 'nm'}
            ],
            file_sets=[
                {
                    'id': 'images',
                    'name': 'Images',
                    'encoding_format': 'image/tiff',
                    'includes': 'images/**/*.tif',
                }
            ],
            field_is_array=True,
            field_array_shape='512,512,4',
        )
        assert isinstance(result, ScaffoldResult)
        assert result.valid is True, result.errors
        doc = result.json_ld
        assert doc['conformsTo'][1] == 'http://mlcommons.org/croissant/geo/1.0'
        # GIS-order bbox serialized to spec lat-first ordering.
        assert doc['spatialCoverage']['geo']['box'] == '24.0 -125.0 49.0 -66.0'
        rs = doc['recordSet'][0]
        assert rs['field'][0]['source']['fileSet']['@id'] == 'images'
        assert rs['geocr:spatialResolution']['value'] == 30

    async def test_writes_output_file(self, tools, ctx, monkeypatch, tmp_path):
        monkeypatch.setenv('GEOCR_OUTPUT_DIR', str(tmp_path))
        result = await tools.create_geocroissant_scaffold(
            ctx, name='Written Dataset', output_filename='out.json'
        )
        assert result.path is not None
        written = json.loads(open(result.path, encoding='utf-8').read())
        assert written['name'] == 'Written Dataset'

    async def test_array_shape_requires_is_array(self, tools, ctx):
        with pytest.raises(ValueError, match='field_is_array'):
            await tools.create_geocroissant_scaffold(ctx, name='X', field_array_shape='10,10')

    async def test_missing_name_raises(self, tools, ctx):
        with pytest.raises(ValueError, match='name'):
            await tools.create_geocroissant_scaffold(ctx, name=' ')

    async def test_file_object_without_url_raises(self, tools, ctx):
        with pytest.raises(ValueError, match='content_url'):
            await tools.create_geocroissant_scaffold(ctx, name='X', file_objects=[{'id': 'f1'}])


class TestGetSpecReference:
    async def test_all_topics(self, tools, ctx):
        text = await tools.get_geocroissant_spec_reference(ctx, topic='all')
        assert 'GeoCroissant' in text
        for section in ('Canonical @context', 'Properties Reference', 'Python API'):
            assert section in text

    @pytest.mark.parametrize('topic', ['overview', 'context', 'properties', 'example'])
    async def test_single_topic(self, tools, ctx, topic):
        text = await tools.get_geocroissant_spec_reference(ctx, topic=topic)
        assert '# ' in text

    async def test_unknown_topic_raises(self, tools, ctx):
        with pytest.raises(ValueError, match='Unknown topic'):
            await tools.get_geocroissant_spec_reference(ctx, topic='bogus')
