"""Unit tests for shared helpers."""

import datetime
import json
import pytest
from copy import deepcopy
from geocr_mcp_server import common


class JsonValue:
    def to_json(self):
        return {'value': 1}


class BrokenJsonValue:
    def to_json(self):
        raise ValueError('cannot serialize')


class StringValue:
    __slots__ = ()

    def __str__(self):
        """Return the stable JSON fallback representation."""
        return 'string-value'


class TestResolveJsonldInput:
    def test_content_wins(self, valid_geocroissant):
        result = common.resolve_jsonld_input(jsonld_content=json.dumps(valid_geocroissant))
        assert result == valid_geocroissant

    def test_path_resolved_absolute(self, valid_geocroissant_file):
        result = common.resolve_jsonld_input(jsonld_path=valid_geocroissant_file)
        assert str(result).endswith('metadata.json')

    def test_url_passthrough(self):
        url = 'https://example.com/metadata.json'
        assert common.resolve_jsonld_input(jsonld_url=url) == url

    def test_no_input_raises(self):
        with pytest.raises(ValueError, match='No input'):
            common.resolve_jsonld_input()

    def test_multiple_inputs_raise(self, tmp_path):
        f = tmp_path / 'm.json'
        f.write_text('{}')
        with pytest.raises(ValueError, match='Multiple inputs'):
            common.resolve_jsonld_input(jsonld_path=str(f), jsonld_url='https://x')

    def test_bad_json_content(self):
        with pytest.raises(ValueError, match='not valid JSON'):
            common.resolve_jsonld_input(jsonld_content='{oops')

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            common.resolve_jsonld_input(jsonld_path='/no/such/file.json')


class TestToJsonSafe:
    def test_primitives(self):
        assert common.to_json_safe(1) == 1
        assert common.to_json_safe('a') == 'a'
        assert common.to_json_safe(None) is None
        assert common.to_json_safe(True) is True

    def test_datetime(self):
        dt = datetime.datetime(2024, 1, 2, 3, 4, 5)
        assert common.to_json_safe(dt) == '2024-01-02T03:04:05'

    def test_nested_containers(self):
        value = {'a': [1, {'b': datetime.date(2020, 12, 31)}]}
        assert common.to_json_safe(value) == {'a': [1, {'b': '2020-12-31'}]}

    def test_language_value(self):
        assert common._language_value({'en': 'hello'}) == 'hello'
        assert common._language_value('plain') == 'plain'

    def test_object_protocols_and_depth_limit(self, tmp_path):
        assert common.to_json_safe(tmp_path / 'value') == str(tmp_path / 'value')
        assert common.to_json_safe(JsonValue()) == {'value': 1}
        assert common.to_json_safe(BrokenJsonValue()) == 'BrokenJsonValue'
        assert common.to_json_safe(StringValue()) == 'string-value'
        assert common.to_json_safe({'nested': 1}, max_depth=0).startswith("{'nested'")
        assert common.from_datetime_to_str_safe(None) is None

    def test_summary_input_forms(self):
        assert common.node_type_name(object()) == 'object'
        assert common.summarize_quantitative(None) is None
        assert common.summarize_quantitative(3) == 3
        assert common.summarize_quantitative({'value': 4}) == {'value': 4}
        assert common.summarize_band_configuration(None) is None
        assert common.summarize_band_configuration('RGB') == 'RGB'
        assert common.summarize_band_configuration({'totalBands': 3}) == {
            'totalBands': 3
        }
        assert common.summarize_spectral_bands(None) is None
        assert common.summarize_spectral_bands([{'name': 'red'}]) == [{'name': 'red'}]


def test_rich_ml_croissant_node_summaries(valid_geocroissant):
    document = deepcopy(valid_geocroissant)
    document.update(
        {
            'url': 'https://example.com/dataset',
            'citeAs': 'Example citation',
            'dateCreated': '2023-01-01',
            'datePublished': '2023-02-01',
            'dateModified': '2023-03-01',
            'creator': [{'@type': 'Organization', 'name': 'Creator'}],
            'publisher': [{'@type': 'Organization', 'name': 'Publisher'}],
            'keywords': ['earth observation'],
            'sameAs': ['https://example.com/same'],
            'geocr:recordEndpoint': 'https://example.com/stac',
            'geocr:spatialBias': 'Northern hemisphere',
            'geocr:samplingStrategy': 'Systematic grid',
            'geocr:multiWavelengthConfiguration': {
                '@type': 'geocr:MultiWavelengthConfiguration',
                'geocr:channelList': ['171A', '193A'],
            },
            'geocr:solarInstrumentCharacteristics': {
                '@type': 'geocr:SolarInstrumentCharacteristics',
                'geocr:observatory': 'SDO',
                'geocr:instrument': 'AIA',
            },
        }
    )
    document['distribution'].append(
        {
            '@type': 'cr:FileObject',
            '@id': 'archive',
            'name': 'Archive',
            'description': 'Download archive.',
            'encodingFormat': 'application/zip',
            'contentUrl': 'https://example.com/archive.zip',
            'sha256': 'a' * 64,
        }
    )
    record_set = document['recordSet'][1]
    record_set.update(
        {
            'description': 'Inline labels.',
            'isEnumeration': True,
            'examples': [{'labels/id': 'example'}],
        }
    )
    record_set['field'][0]['description'] = 'Identifier.'

    metadata = common.load_dataset(document).metadata
    metadata.spatial_index = {'scheme': 'h3'}
    file_object = next(
        entry for entry in metadata.distribution if common.node_type_name(entry) == 'FileObject'
    )
    file_object.content_size = '12 KB'
    file_object.md5 = 'b' * 32
    file_object.contained_in = ['images']
    file_set = next(
        entry for entry in metadata.distribution if common.node_type_name(entry) == 'FileSet'
    )
    record_node = next(entry for entry in metadata.record_sets if entry.uuid == 'labels')
    record_node.spatial_resolution = '30 m'
    record_node.temporal_resolution = {'value': 1, 'unitText': 'days'}
    record_node.spatial_index = {'scheme': 'h3'}
    record_node.time_series_index = 'labels/id'
    record_node.is_enumeration = True
    field = record_node.fields[0]
    field.value = {'constant': True}
    field.references = record_node.fields[1]
    field.sub_fields = [record_node.fields[2]]
    field.band_configuration = metadata.band_configuration
    field.spectral_band_metadata = metadata.spectral_band_metadata

    summary = common.summarize_metadata(metadata)
    assert summary['url'] == 'https://example.com/dataset'
    assert summary['citeAs'] == 'Example citation'
    assert summary['creator'] == ['Creator']
    assert summary['publisher'] == ['Publisher']
    assert summary['keywords'] == ['earth observation']
    assert summary['sameAs'] == ['https://example.com/same']
    assert summary['geospatial']['recordEndpoint'] == 'https://example.com/stac'
    assert summary['geospatial']['multiWavelengthConfiguration']['channelList'] == [
        '171A',
        '193A',
    ]
    assert summary['geospatial']['solarInstrumentCharacteristics'] == {
        'observatory': 'SDO',
        'instrument': 'AIA',
    }

    distribution = {entry['@id']: entry for entry in summary['distribution']}
    assert distribution['archive']['contentSize'] == '12 KB'
    assert distribution['archive']['md5'] == 'b' * 32
    assert distribution['archive']['sha256'] == 'a' * 64
    assert distribution['archive']['containedIn'] == ['images']

    labels = next(entry for entry in summary['record_sets'] if entry['@id'] == 'labels')
    assert labels['description'] == 'Inline labels.'
    assert labels['isEnumeration'] is True
    assert labels['num_examples'] == 1
    assert labels['spatialIndex'] == {'scheme': 'h3'}
    assert labels['timeSeriesIndex'] == 'labels/id'
    assert labels['fields'][0]['description'] == 'Identifier.'
    assert labels['fields'][0]['value'] == {'constant': True}
    assert labels['fields'][0]['references'] == 'labels/burned'
    assert labels['fields'][0]['subField'][0]['@id'] == 'labels/region'
    assert labels['fields'][0]['bandConfiguration']['totalBands'] == 6
    assert labels['fields'][0]['spectralBandMetadata'][0]['name'] == 'Blue'

    file_set.includes = []
    assert 'includes' not in common.summarize_distribution(metadata)[0]
    record_node.time_series_index = record_node.fields[0]
    assert common.summarize_record_set(record_node)['timeSeriesIndex'] == 'labels/id'

    quantitative = metadata.spatial_resolution
    quantitative.value = None
    quantitative.unitText = None
    assert common.summarize_quantitative(quantitative) == {
        '@type': 'QuantitativeValue'
    }

    band_configuration = metadata.band_configuration
    band_configuration.total_bands = None
    band_configuration.band_names_list = []
    assert common.summarize_band_configuration(band_configuration) == {
        '@type': 'BandConfiguration'
    }

    spectral_band = metadata.spectral_band_metadata[0]
    spectral_band.name = None
    spectral_band.bandwidth = spectral_band.center_wavelength
    spectral_band.center_wavelength = None
    spectral_summary = common.summarize_spectral_bands([spectral_band])[0]
    assert 'name' not in spectral_summary
    assert 'centerWavelength' not in spectral_summary
    assert spectral_summary['bandwidth']['value'] == 490

    file_object.encoding_formats = []
    file_object.content_url = None
    file_object.content_size = None
    file_object.md5 = None
    file_object.sha256 = None
    file_set.contained_in = [file_object]
    sparse_distribution = common.summarize_distribution(metadata)
    sparse_archive = next(entry for entry in sparse_distribution if entry['@id'] == 'archive')
    assert 'encodingFormat' not in sparse_archive
    assert 'contentUrl' not in sparse_archive
    assert sparse_distribution[0]['containedIn'] == ['archive']
    file_set.contained_in = [None]
    assert 'containedIn' not in common.summarize_distribution(metadata)[0]

    field.data_types = []
    field.is_array = True
    field.array_shape = None
    sparse_field = common.summarize_field(field)
    assert 'dataType' not in sparse_field
    assert sparse_field['isArray'] is True
    assert 'arrayShape' not in sparse_field

    record_node.key = []
    assert 'key' not in common.summarize_record_set(record_node)

    metadata.creators[0].name = ''
    fallback_creator = common.summarize_metadata(metadata)['creator'][0]
    assert fallback_creator == metadata.creators[0].uuid


class TestSecureOutputPath:
    def test_traversal_blocked(self, monkeypatch, tmp_path):
        monkeypatch.setenv('GEOCR_OUTPUT_DIR', str(tmp_path))
        path = common.secure_output_path('../../etc/passwd.json')
        assert path.parent == tmp_path
        assert path.name == 'passwd.json'

    def test_default_dir_created(self, monkeypatch):
        monkeypatch.delenv('GEOCR_OUTPUT_DIR', raising=False)
        path = common.secure_output_path('out.json', output_dir=None)
        assert path.name == 'out.json'
        assert path.parent.exists()

    def test_empty_filename_raises(self):
        with pytest.raises(ValueError, match='must not be empty'):
            common.secure_output_path('   ')


class TestWriteJsonLd:
    def test_roundtrip(self, tmp_path, valid_geocroissant):
        path = common.write_json_ld(valid_geocroissant, tmp_path / 'doc.json')
        assert json.loads(path.read_text(encoding='utf-8')) == valid_geocroissant
