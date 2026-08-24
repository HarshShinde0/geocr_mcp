"""Shared fixtures for geocr-mcp-server tests."""

import json
import pytest
from geocr_mcp_server.spec import official_context


@pytest.fixture
def valid_geocroissant() -> dict:
    """A minimal valid GeoCroissant document (v1.1 + geo).

    Contains one FileSet-backed RecordSet (no downloads needed for static
    analysis) and one RecordSet with inline `cr:data` so that record
    materialization can be tested fully offline.
    """
    return {
        '@context': official_context(),
        '@type': 'Dataset',
        'name': 'Test Burn Scars',
        'description': 'HLS burn scars test fixture.',
        'license': 'https://creativecommons.org/licenses/by/4.0/',
        'version': '1.0',
        'conformsTo': [
            'http://mlcommons.org/croissant/1.1',
            'http://mlcommons.org/croissant/geo/1.0',
        ],
        'spatialCoverage': {
            '@type': 'Place',
            'geo': {'@type': 'GeoShape', 'box': '24.0 -125.0 49.0 -66.0'},
        },
        'temporalCoverage': '2018-01-01/2021-12-31',
        'geocr:coordinateReferenceSystem': 'EPSG:4326',
        'geocr:spatialResolution': {
            '@type': 'QuantitativeValue',
            'value': 30,
            'unitText': 'm',
        },
        'geocr:temporalResolution': {
            '@type': 'QuantitativeValue',
            'value': 2,
            'unitText': 'days',
        },
        'geocr:bandConfiguration': {
            '@type': 'geocr:BandConfiguration',
            'geocr:totalBands': 6,
            'geocr:bandNamesList': ['Blue', 'Green', 'Red', 'NIR', 'SW1', 'SW2'],
        },
        'geocr:spectralBandMetadata': [
            {
                '@type': 'geocr:SpectralBand',
                'name': 'Blue',
                'geocr:centerWavelength': {
                    '@type': 'QuantitativeValue',
                    'value': 490,
                    'unitText': 'nm',
                },
            }
        ],
        'distribution': [
            {
                '@type': 'cr:FileSet',
                '@id': 'images',
                'name': 'Images',
                'encodingFormat': 'image/tiff',
                'includes': 'images/**/*.tif',
            }
        ],
        'recordSet': [
            {
                '@type': 'cr:RecordSet',
                '@id': 'images_recordset',
                'name': 'Images',
                'key': {'@id': 'images_recordset/image'},
                'field': [
                    {
                        '@type': 'cr:Field',
                        '@id': 'images_recordset/image',
                        'name': 'image',
                        'dataType': 'sc:ImageObject',
                        'source': {
                            'fileSet': {'@id': 'images'},
                            'extract': {'fileProperty': 'content'},
                        },
                        'isArray': True,
                        'arrayShape': '512,512,6',
                    }
                ],
            },
            {
                '@type': 'cr:RecordSet',
                '@id': 'labels',
                'name': 'Labels',
                'key': {'@id': 'labels/id'},
                'field': [
                    {
                        '@type': 'cr:Field',
                        '@id': 'labels/id',
                        'name': 'id',
                        'dataType': 'sc:Text',
                    },
                    {
                        '@type': 'cr:Field',
                        '@id': 'labels/burned',
                        'name': 'burned',
                        'dataType': 'sc:Boolean',
                    },
                    {
                        '@type': 'cr:Field',
                        '@id': 'labels/region',
                        'name': 'region',
                        'dataType': 'sc:Text',
                    },
                ],
                'data': [
                    {'labels/id': 'a1', 'labels/burned': True, 'labels/region': 'north'},
                    {'labels/id': 'a2', 'labels/burned': False, 'labels/region': 'south'},
                    {'labels/id': 'a3', 'labels/burned': True, 'labels/region': 'east'},
                ],
            },
        ],
    }


@pytest.fixture
def valid_geocroissant_file(tmp_path, valid_geocroissant) -> str:
    """Writes the valid fixture to disk and returns its path."""
    path = tmp_path / 'metadata.json'
    path.write_text(json.dumps(valid_geocroissant), encoding='utf-8')
    return str(path)


@pytest.fixture
def invalid_geocroissant_content(valid_geocroissant) -> str:
    """A GeoCroissant document with a field defining both source and value."""
    broken = json.loads(json.dumps(valid_geocroissant))
    broken['recordSet'][0]['field'][0]['value'] = 'conflict'
    return json.dumps(broken)


@pytest.fixture
def malformed_json_content() -> str:
    """Inline content that is not valid JSON at all."""
    return '{"@context": broken'
