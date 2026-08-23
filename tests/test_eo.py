"""Unit tests for EO discovery and STAC -> GeoCroissant generation.

Offline by default; live STAC calls are marked `live` and deselected with
`-m "not live"` (the default selection).
"""

import pytest
from geocr_mcp_server import catalogs, common, eo


def _band(name, center, width=None):
    band = {'name': name, 'center_wavelength': center}
    if width is not None:
        band['bandwidth'] = width
    return band


def _fake_item(item_id='S2_20230715', cloud=12.5, dt='2023-07-15T18:55:31Z') -> dict:
    """Minimal Sentinel-2-like STAC item dict (Earth Search asset layout)."""
    return {
        'id': item_id,
        'collection': 'sentinel-2-c1-l2a',
        'bbox': [-125.5, 47.0, -124.5, 48.0],
        'properties': {
            'datetime': dt,
            'platform': 'sentinel-2b',
            'eo:cloud_cover': cloud,
            'proj:epsg': 32610,
        },
        'assets': {
            'thumbnail': {
                'href': f'https://example.com/{item_id}.jpg',
                'type': 'image/jpeg',
            },
            'blue': {
                'href': f'https://example.com/{item_id}_B02.tif',
                'type': 'image/tiff',
                'eo:bands': [_band('B02', 0.49, 0.098)],
            },
            'green': {
                'href': f'https://example.com/{item_id}_B03.tif',
                'type': 'image/tiff',
                'eo:bands': [_band('B03', 0.56)],
            },
            'red': {
                'href': f'https://example.com/{item_id}_B04.tif',
                'type': 'image/tiff',
                'eo:bands': [_band('B04', 0.665, 0.038)],
            },
            'nir': {
                'href': f'https://example.com/{item_id}_B08.tif',
                'type': 'image/tiff',
                'eo:bands': [_band('B08', 0.842)],
            },
        },
    }


class TestCatalogRegistry:
    def test_single_registered_catalog(self):
        assert list(catalogs.get_config()['catalogs']) == ['earth-search']
        cat = eo.get_catalog()
        assert cat['id'] == 'earth-search'
        assert cat['url'] == 'https://earth-search.aws.element84.com/v1'

    def test_audited_collection_ids(self):
        """Curated ids must be a subset of the audited live API collections."""
        audited = {
            'sentinel-2-c1-l2a',
            'sentinel-2-l2a',
            'sentinel-2-l1c',
            'sentinel-2-pre-c1-l2a',
            'landsat-c2-l2',
            'sentinel-1-grd',
            'cop-dem-glo-30',
            'cop-dem-glo-90',
            'naip',
        }
        common_colls = {
            c
            for colls in catalogs.get_config()['catalogs']['earth-search']['common'].values()
            for c in colls
        }
        assert common_colls <= audited

    def test_modalities_from_yaml(self):
        assert set(catalogs.modalities()) == {'optical', 'radar', 'elevation'}

    def test_unknown_catalog_raises(self):
        with pytest.raises(ValueError, match='Unknown catalog'):
            eo.get_catalog('planetary-computer')

    def test_default_collections_for_modality(self):
        optical = eo.default_collections_for('optical')
        assert 'sentinel-2-c1-l2a' in optical
        all_colls = eo.default_collections_for(None)
        assert 'sentinel-1-grd' in all_colls and 'cop-dem-glo-30' in all_colls


class TestTopics:
    def test_resolve_known_topic(self):
        topics, colls = eo.resolve_topic('flood mapping near lisbon')
        assert topics == ['flood']
        assert colls == ['sentinel-1-grd', 'sentinel-2-c1-l2a']

    def test_resolve_multiple_topics_dedupes(self):
        topics, colls = eo.resolve_topic('wildfire ndvi')
        assert set(topics) == {'wildfire', 'ndvi'}
        assert len(colls) == len(set(colls))
        assert 'landsat-c2-l2' in colls and 'sentinel-2-c1-l2a' in colls

    def test_resolve_unknown_falls_back_to_multimodal(self):
        topics, colls = eo.resolve_topic('something arbitrary xyz')
        assert topics == []
        assert set(colls) == {'sentinel-2-c1-l2a', 'sentinel-1-grd'}

    def test_every_topic_collection_is_curated(self):
        known = {
            c
            for colls in catalogs.get_config()['catalogs']['earth-search']['common'].values()
            for c in colls
        }
        for topic, colls in catalogs.topics().items():
            assert set(colls) <= known, topic


class TestModalityHeuristics:
    @pytest.mark.parametrize(
        ('text', 'expected'),
        [
            ('sentinel-1-grd SAR GRD', 'radar'),
            ('cop-dem-glo-30 elevation', 'elevation'),
            ('Sentinel-2 L2A surface reflectance', 'optical'),
            ('NAIP aerial orthoimagery', 'optical'),
            ('totally-unrelated-thing', None),
        ],
    )
    def test_guess_modality(self, text, expected):
        assert eo.guess_modality({'id': text.lower().replace(' ', '-')}) == expected

    def test_keywords_considered(self):
        assert eo.guess_modality({'id': 'weird-id', 'keywords': ['SAR', 'radar']}) == 'radar'


class TestSearchScenesValidation:
    def test_bad_bbox_length(self):
        with pytest.raises(ValueError, match='bbox'):
            eo.search_scenes(bbox=[1.0, 2.0, 3.0])

    def test_out_of_range_bbox(self):
        with pytest.raises(ValueError, match='Longitude'):
            eo.search_scenes(bbox=[-500, 0, 100, 10])

    def test_inverted_lat(self):
        with pytest.raises(ValueError, match='min_lat'):
            eo.search_scenes(bbox=[0, 40, 10, 10])

    def test_no_collections_raises(self):
        with pytest.raises(ValueError, match='No known collections'):
            eo.search_scenes(bbox=[0, 0, 1, 1], collections=[])


class TestCatalogConfigOverride:
    def test_env_override(self, tmp_path, monkeypatch):
        override = tmp_path / 'custom.yaml'
        override.write_text(
            'modalities:\n  - optical\n'
            'catalogs:\n'
            '  my-catalog:\n'
            '    url: https://example.com/stac\n'
            '    common:\n'
            '      optical: ["coll-a"]\n'
            'topics:\n'
            '  custom: ["coll-a"]\n',
            encoding='utf-8',
        )
        monkeypatch.setenv(catalogs.CONFIG_ENV_VAR, str(override))
        catalogs.reload_config()
        try:
            assert list(catalogs.get_config()['catalogs']) == ['my-catalog']
            assert catalogs.topics() == {'custom': ['coll-a']}
            assert eo.get_catalog('my-catalog')['url'] == 'https://example.com/stac'
        finally:
            monkeypatch.delenv(catalogs.CONFIG_ENV_VAR)
            catalogs.reload_config()

    def test_invalid_yaml_raises(self, tmp_path, monkeypatch):
        bad = tmp_path / 'bad.yaml'
        bad.write_text('catalogs: [unclosed', encoding='utf-8')
        monkeypatch.setenv(catalogs.CONFIG_ENV_VAR, str(bad))
        catalogs.reload_config()
        try:
            with pytest.raises(ValueError, match='Invalid YAML'):
                catalogs.get_config()
        finally:
            monkeypatch.delenv(catalogs.CONFIG_ENV_VAR)
            catalogs.reload_config()


class TestGeocroissantFromStac:
    def _build(self, items):
        return eo.geocroissant_from_stac(
            name='Test EO Dataset',
            description='Generated from fake STAC results.',
            license_url='https://creativecommons.org/licenses/by/4.0/',
            creators=['NASA'],
            raw_items=items,
        )

    def test_empty_items_raise(self):
        with pytest.raises(ValueError, match='No STAC scenes'):
            self._build([])

    def test_document_structure_and_validation(self):
        doc = self._build([_fake_item(), _fake_item('S2_20230801', dt='2023-08-01T18:55:31Z')])
        assert doc['conformsTo'] == [
            'http://mlcommons.org/croissant/1.1',
            'http://mlcommons.org/croissant/geo/1.0',
        ]
        assert doc['geocr:coordinateReferenceSystem'] == 'EPSG:4326'
        assert doc['geocr:recordEndpoint'] == ('https://earth-search.aws.element84.com/v1')
        # Bands ordered by center wavelength; micrometers converted to nm.
        bands = doc['geocr:bandConfiguration']
        assert bands['geocr:totalBands'] == 4
        assert bands['geocr:bandNamesList'] == ['B02', 'B03', 'B04', 'B08']
        spectral = doc['geocr:spectralBandMetadata']
        blue = next(e for e in spectral if e['name'] == 'B02')
        assert blue['@type'] == 'geocr:SpectralBand'
        assert blue['geocr:centerWavelength']['value'] == pytest.approx(490.0)
        assert blue['geocr:centerWavelength']['unitText'] == 'nm'
        red = next(e for e in spectral if e['name'] == 'B04')
        assert red['geocr:bandwidth']['value'] == pytest.approx(38.0)
        # Coverage: union of both identical bboxes.
        box = doc['spatialCoverage']['geo']['box']
        assert box == '47.0 -125.5 48.0 -124.5'
        assert doc['temporalCoverage'] == '2023-07-15/2023-08-01'
        # Distribution: capped http asset FileObjects (no checksums needed).
        assert 0 < len(doc['distribution']) <= 6
        assert all(d['contentUrl'].startswith('https://') for d in doc['distribution'])
        # RecordSet: inline rows keyed exactly like field ids.
        rs = doc['recordSet'][0]
        field_ids = {f['@id'] for f in rs['field']}
        assert field_ids == {
            f'scenes/{n}'
            for n in ('scene_id', 'collection', 'datetime', 'cloud_cover', 'epsg', 'image_url')
        }
        assert len(rs['data']) == 2
        row = rs['data'][0]
        assert set(row.keys()) == field_ids
        assert row['scenes/scene_id'] == 'S2_20230715'
        assert row['scenes/cloud_cover'] == 12.5
        assert row['scenes/epsg'] == 32610
        assert row['scenes/image_url'].endswith('B02.tif')
        # The generated document must pass the official validator offline.
        dataset = common.load_dataset(doc)
        assert dataset.metadata.name == 'Test EO Dataset'

    def test_field_band_configuration_attached_to_image_url(self):
        doc = self._build([_fake_item()])
        image_field = doc['recordSet'][0]['field'][-1]
        assert image_field['@id'] == 'scenes/image_url'
        assert image_field['geocr:bandConfiguration']['geocr:totalBands'] == 4


class TestEoToolsOffline:
    async def test_list_catalogs_tool(self):
        from geocr_mcp_server.tools import GeoCroissantTools
        from unittest.mock import AsyncMock

        result = await GeoCroissantTools().list_eo_catalogs(AsyncMock())
        assert result['catalogs'][0]['id'] == 'earth-search'
        assert 'flood' in result['catalogs'][0]['topics']

    async def test_search_datasets_unknown_modality(self):
        from geocr_mcp_server.tools import GeoCroissantTools
        from unittest.mock import AsyncMock

        tools = GeoCroissantTools()
        with pytest.raises(ValueError, match='Unknown modality'):
            await tools.search_eo_datasets(AsyncMock(), modality='ultraviolet')

    async def test_search_scenes_invalid_input(self):
        from geocr_mcp_server.tools import GeoCroissantTools
        from unittest.mock import AsyncMock

        tools = GeoCroissantTools()
        with pytest.raises(ValueError, match='bbox'):
            await tools.search_eo_scenes(AsyncMock(), bbox=[0, 1])


@pytest.mark.live
class TestLiveStacSearch:
    async def test_live_scene_search_and_generation(self):
        """Live end-to-end: search Sentinel-2 over Lisbon, generate metadata."""
        search = eo.search_scenes(
            bbox=[-9.5, 38.6, -9.0, 38.9],
            modality='optical',
            datetime_range='2023-07-01/2023-09-30',
            max_cloud_cover=10,
            limit=2,
        )
        assert search['scene_count'] >= 1
        doc = eo.geocroissant_from_stac(
            name='Lisbon S2 Summer 2023',
            description='Live STAC smoke test.',
            license_url='',
            creators=None,
            raw_items=search['_raw_items'],
        )
        dataset = common.load_dataset(doc)
        assert dataset.metadata.record_sets[0].uuid.startswith('scenes')

    async def test_live_topic_search(self):
        result = eo.search_collections(query='flood')
        assert result['matched_topics'] == ['flood']
        ids = {c['collection'] for c in result['collections']}
        assert {'sentinel-1-grd', 'sentinel-2-c1-l2a'} <= ids
