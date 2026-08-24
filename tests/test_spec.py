"""GeoCroissant scaffold construction tests."""

import pytest
from geocr_mcp_server import common, spec


def test_rich_scaffold_with_file_object_is_valid():
    document = spec.build_scaffold(
        name='Rich Dataset',
        description='All supported scaffold metadata.',
        license='https://creativecommons.org/licenses/by/4.0/',
        cite_as='Example citation',
        version='1.0',
        date_published='2024-01-01',
        creators=['Example Organization'],
        bbox='-10, 20, 30, 40',
        temporal_coverage='2024-01-01/2024-12-31',
        coordinate_reference_system='EPSG:4326',
        spatial_resolution=10,
        spatial_resolution_unit='',
        temporal_resolution_value=1,
        temporal_resolution_unit='days',
        band_names=['red'],
        file_objects=[
            {
                'id': 'image',
                'name': 'Image',
                'description': 'A source image.',
                'content_url': 'https://example.com/image.tif',
                'encoding_format': 'image/tiff',
                'sha256': 'a' * 64,
                'md5': 'b' * 32,
            }
        ],
        field_is_array=True,
    )

    assert document['citeAs'] == 'Example citation'
    assert document['datePublished'] == '2024-01-01'
    assert document['creator'][0]['name'] == 'Example Organization'
    assert document['geocr:spatialResolution'] == {
        '@type': 'QuantitativeValue',
        'value': 10,
    }
    distribution = document['distribution'][0]
    assert distribution['sha256'] == 'a' * 64
    assert distribution['md5'] == 'b' * 32
    field = document['recordSet'][0]['field'][0]
    assert field['isArray'] is True
    assert 'arrayShape' not in field
    assert field['source']['fileObject']['@id'] == 'image'
    assert document['recordSet'][0]['geocr:temporalResolution']['value'] == 1
    assert common.load_dataset(document).metadata.name == 'Rich Dataset'


def test_distribution_containment_and_record_set_omission():
    document = spec.build_scaffold(
        name='Contained Dataset',
        file_sets=[
            {
                'id': 'archive',
                'description': 'Archive members.',
                'contained_in': 'container',
            }
        ],
        file_objects=[
            {
                'id': 'member',
                'contained_in': 'archive',
                'description': 'Contained member.',
            },
            {'id': 'remote', 'content_url': 'https://example.com/remote.bin'},
        ],
        record_set_name=None,
    )

    assert document['distribution'][0]['containedIn'] == {'@id': 'container'}
    assert document['distribution'][1]['containedIn'] == {'@id': 'archive'}
    assert 'contentUrl' not in document['distribution'][1]
    assert 'recordSet' not in document


@pytest.mark.parametrize(
    ('band', 'center', 'width'),
    [
        (
            {
                'name': 'a',
                'geocr:centerWavelength': {
                    '@type': 'QuantitativeValue',
                    'value': 1,
                },
                'geocr:bandwidth': {'@type': 'QuantitativeValue', 'value': 2},
            },
            {'@type': 'QuantitativeValue', 'value': 1},
            {'@type': 'QuantitativeValue', 'value': 2},
        ),
        (
            {
                'name': 'b',
                'centerWavelength': {'value': 3, 'unit': 'um'},
                'bandwidth': {'value': 4, 'unitText': 'um'},
            },
            {'@type': 'QuantitativeValue', 'value': 3, 'unitText': 'um'},
            {'@type': 'QuantitativeValue', 'value': 4, 'unitText': 'um'},
        ),
        (
            {
                'name': 'c',
                'centerWavelength': 5,
                'bandwidth': 6,
                'unit': 'nm',
            },
            {'@type': 'QuantitativeValue', 'value': 5, 'unitText': 'nm'},
            {'@type': 'QuantitativeValue', 'value': 6, 'unitText': 'nm'},
        ),
        (
            {
                'name': 'd',
                'centerWavelengthValue': 7,
                'centerWavelengthUnit': '',
                'bandwidthValue': 8,
                'bandwidthUnit': '',
            },
            {'@type': 'QuantitativeValue', 'value': 7},
            {'@type': 'QuantitativeValue', 'value': 8},
        ),
        (
            {
                'name': 'e',
                'centerWavelength': {'unit': 'nm'},
                'bandwidth': {},
            },
            None,
            None,
        ),
        ({'name': 'f'}, None, None),
    ],
)
def test_spectral_band_input_forms(band, center, width):
    result = spec._spectral_band(band)
    assert result.get('geocr:centerWavelength') == center
    assert result.get('geocr:bandwidth') == width


@pytest.mark.parametrize(
    ('bbox', 'message'),
    [
        ('1,2,3', 'exactly 4'),
        ('1,2,no,4', 'must be numbers'),
        ([1, 2, 3], 'exactly 4'),
    ],
)
def test_invalid_bbox_forms(bbox, message):
    with pytest.raises(ValueError, match=message):
        spec.build_scaffold(name='Dataset', bbox=bbox)
