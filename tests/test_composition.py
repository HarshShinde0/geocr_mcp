"""Tests for combining independent STAC searches into one GeoCroissant dataset."""

import pytest
from geocr_mcp_server import composition
from tests.test_eo import _stac_item, _veda_stac_item


def _source(
    source_id: str,
    catalog_id: str,
    collection_id: str,
    bbox: list[float],
    **filters,
) -> dict:
    return {
        'source_id': source_id,
        'catalog_id': catalog_id,
        'collection_id': collection_id,
        'bbox': bbox,
        **filters,
    }


def test_search_sources_runs_each_query_independently(monkeypatch):
    calls = []
    items = {
        'catalog-a': [_stac_item()],
        'catalog-b': [_veda_stac_item()],
    }

    def fake_search_scenes(**kwargs):
        calls.append(kwargs)
        catalog_id = kwargs['catalog_id']
        return {
            'catalog': catalog_id,
            'catalog_name': catalog_id,
            'collections_searched': kwargs['collections'],
            'bbox': kwargs['bbox'],
            'datetime_range': kwargs['datetime_range'],
            'max_cloud_cover': kwargs['max_cloud_cover'],
            'cloud_filter_applied': kwargs['max_cloud_cover'] is not None,
            'notes': [],
            'scene_count': len(items[catalog_id]),
            'scenes': [],
            '_raw_items': items[catalog_id],
        }

    monkeypatch.setattr(composition.eo, 'search_scenes', fake_search_scenes)
    results = composition.search_sources(
        [
            _source(
                'source-a',
                'catalog-a',
                'collection-a',
                [-53, -31, -50, -28],
                datetime_range='2026-08-01/2026-08-25',
                max_cloud_cover=20,
                limit=3,
            ),
            _source(
                'source-b',
                'catalog-b',
                'collection-b',
                [-180, -90, 180, 90],
                limit=2,
            ),
        ]
    )


    assert [result['source_id'] for result in results] == ['source-a', 'source-b']
    assert calls[0]['collections'] == ['collection-a']
    assert calls[0]['max_cloud_cover'] == 20
    assert calls[0]['limit'] == 3
    assert calls[1]['collections'] == ['collection-b']
    assert calls[1]['max_cloud_cover'] is None
    assert calls[1]['limit'] == 2


@pytest.mark.parametrize(
    ('sources', 'message'),
    [
        ([], 'at least one source'),
        ([None], 'must be an object'),
        ([{}], 'catalog_id'),
        (
            [
                {
                    'catalog_id': 'catalog-a',
                    'collection_id': 'collection-a',
                    'bbox': [0, 0, 1, 1],
                    'source_id': ' ',
                }
            ],
            'source_id',
        ),
        (
            [
                {
                    'catalog_id': 'catalog-a',
                    'collection_id': 'collection-a',
                    'bbox': '0,0,1,1',
                }
            ],
            'bbox',
        ),
        (
            [
                {
                    'catalog_id': 'catalog-a',
                    'collection_id': 'collection-a',
                    'bbox': [0, 0, 1, 1],
                    'limit': 0,
                }
            ],
            'limit',
        ),
        (
            [
                _source('same', 'earth-search', 'a', [0, 0, 1, 1]),
                _source('same', 'veda', 'b', [0, 0, 1, 1]),
            ],
            'source_id',
        ),
        (
            [
                _source('same-id', 'earth-search', 'a', [0, 0, 1, 1]),
                _source('same_id', 'veda', 'b', [0, 0, 1, 1]),
            ],
            'source_id',
        ),
        ([_source('---', 'earth-search', 'a', [0, 0, 1, 1])], 'letter or number'),
    ],
)
def test_search_sources_rejects_invalid_plans(sources, message):
    with pytest.raises(ValueError, match=message):
        composition.search_sources(sources)


def test_compose_document_keeps_sources_separate_and_valid():
    optical = _stac_item(item_id='shared-id')
    atmospheric = _veda_stac_item()
    atmospheric['id'] = 'shared-id'
    results = [
        {
            'source_id': 'optical',
            'catalog_id': 'earth-search',
            'collection_id': 'sentinel-2-c1-l2a',
            'search': {'_raw_items': [optical]},
        },
        {
            'source_id': 'atmosphere',
            'catalog_id': 'veda',
            'collection_id': 'no2-monthly',
            'search': {'_raw_items': [atmospheric]},
        },
    ]

    document = composition.compose_document(
        name='Composite dataset',
        description='Independent source searches.',
        license_url='',
        creators=['Example'],
        source_results=results,
    )

    assert 'geocr:recordEndpoint' not in document
    assert 'geocr:bandConfiguration' not in document
    assert {record_set['@id'] for record_set in document['recordSet']} == {
        'scenes_optical',
        'scenes_atmosphere',
    }
    distribution_ids = [entry['@id'] for entry in document['distribution']]
    assert len(distribution_ids) == len(set(distribution_ids))
    assert any(url['contentUrl'].startswith('s3://') for url in document['distribution'])

    rows = [row for record_set in document['recordSet'] for row in record_set['data']]
    assert {next(value for key, value in row.items() if key.endswith('/source_id')) for row in rows} == {
        'optical',
        'atmosphere',
    }


def test_same_catalog_can_supply_multiple_collections(monkeypatch):
    calls = []

    def fake_search_scenes(**kwargs):
        calls.append(kwargs)
        item = _stac_item(item_id=kwargs['collections'][0])
        item['collection'] = kwargs['collections'][0]
        return {
            'catalog': kwargs['catalog_id'],
            'catalog_name': kwargs['catalog_id'],
            'collections_searched': kwargs['collections'],
            'bbox': kwargs['bbox'],
            'datetime_range': None,
            'max_cloud_cover': None,
            'cloud_filter_applied': False,
            'notes': [],
            'scene_count': 1,
            'scenes': [],
            '_raw_items': [item],
        }

    monkeypatch.setattr(composition.eo, 'search_scenes', fake_search_scenes)
    results = composition.search_sources(
        [
            _source('first', 'catalog-a', 'collection-a', [0, 0, 1, 1]),
            _source('second', 'catalog-a', 'collection-b', [1, 1, 2, 2]),
        ]
    )

    assert [call['catalog_id'] for call in calls] == ['catalog-a', 'catalog-a']
    assert [result['collection_id'] for result in results] == [
        'collection-a',
        'collection-b',
    ]


def test_asset_manifest_preserves_provider_facts():
    item = _veda_stac_item()
    manifest = composition.asset_manifest(
        [
            {
                'source_id': 'veda-source',
                'catalog_id': 'veda',
                'collection_id': 'no2-monthly',
                'search': {'_raw_items': [item]},
            }
        ]
    )

    assert manifest == [
        {
            'source_id': 'veda-source',
            'catalog_id': 'veda',
            'collection_id': 'no2-monthly',
            'scene_id': 'no2-2020-01',
            'asset_key': 'cog_default',
            'href': 's3://veda-data-store/no2/2020-01.tif',
            'media_type': 'image/tiff; application=geotiff; profile=cloud-optimized',
            'roles': ['data'],
            'epsg': 4326,
            'bands': [{'name': 'NO2', 'data_type': 'float32'}],
        }
    ]


def test_asset_manifest_ignores_assets_without_an_href():
    item = _stac_item()
    item['assets'] = {'missing': {'roles': ['data']}}

    assert (
        composition.asset_manifest(
            [
                {
                    'source_id': 'source-a',
                    'catalog_id': 'catalog-a',
                    'collection_id': 'collection-a',
                    'search': {'_raw_items': [item]},
                }
            ]
        )
        == []
    )
