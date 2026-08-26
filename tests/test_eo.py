"""EO discovery and STAC -> GeoCroissant tests."""

import pystac
import pytest
from datetime import datetime
from geocr_mcp_server import catalogs, common, eo


def _band(name, center, width=None):
    band = {'name': name, 'center_wavelength': center}
    if width is not None:
        band['bandwidth'] = width
    return band


def _geometry(bbox):
    west, south, east, north = bbox
    return {
        'type': 'Polygon',
        'coordinates': [
            [[west, south], [east, south], [east, north], [west, north], [west, south]]
        ],
    }


def _stac_item(item_id='S2_20230715', cloud=12.5, dt='2023-07-15T18:55:31Z') -> dict:
    """Build a valid STAC Item through pystac rather than a response stub."""
    bbox = [-125.5, 47.0, -124.5, 48.0]
    item = pystac.Item(
        id=item_id,
        geometry=_geometry(bbox),
        bbox=bbox,
        datetime=datetime.fromisoformat(dt.replace('Z', '+00:00')),
        properties={'platform': 'sentinel-2b', 'eo:cloud_cover': cloud, 'proj:epsg': 32610},
        collection='sentinel-2-c1-l2a',
    )
    item.add_asset(
        'thumbnail',
        pystac.Asset(href=f'https://example.com/{item_id}.jpg', media_type='image/jpeg'),
    )
    for key, band in {
        'blue': _band('B02', 0.49, 0.098),
        'green': _band('B03', 0.56),
        'red': _band('B04', 0.665, 0.038),
        'nir': _band('B08', 0.842),
    }.items():
        item.add_asset(
            key,
            pystac.Asset(
                href=f'https://example.com/{item_id}_{band["name"]}.tif',
                media_type='image/tiff',
                roles=['data'],
                extra_fields={'eo:bands': [band]},
            ),
        )
    return item.to_dict()


def _veda_stac_item() -> dict:
    bbox = [-180.0, -90.0, 180.0, 90.0]
    item = pystac.Item(
        id='no2-2020-01',
        geometry=_geometry(bbox),
        bbox=bbox,
        datetime=None,
        start_datetime=datetime.fromisoformat('2020-01-01T00:00:00+00:00'),
        end_datetime=datetime.fromisoformat('2020-01-31T23:59:59+00:00'),
        properties={},
        collection='no2-monthly',
    )
    item.add_asset(
        'cog_default',
        pystac.Asset(
            href='s3://veda-data-store/no2/2020-01.tif',
            media_type='image/tiff; application=geotiff; profile=cloud-optimized',
            roles=['data'],
            extra_fields={
                'proj:code': 'EPSG:4326',
                'raster:bands': [{'name': 'NO2', 'data_type': 'float32'}],
            },
        ),
    )
    return item.to_dict()


class TestCatalogRegistry:
    def test_yaml_registry_integrity(self):
        config = catalogs.get_config()
        configured = config['catalogs']
        assert configured
        assert config['default_catalog'] in configured

        listed = {catalog['id']: catalog for catalog in catalogs.list_catalogs()}
        assert set(listed) == set(configured)
        for catalog_id, entry in configured.items():
            loaded = catalogs.get_catalog(catalog_id.upper())
            assert loaded['id'] == catalog_id
            assert loaded['name'].strip()
            assert loaded['description'].strip()
            assert loaded['url'].startswith('https://')
            assert loaded['collections']
            assert len(loaded['collections']) == len(set(loaded['collections']))
            assert listed[catalog_id]['collection_discovery'] == 'live'
            assert listed[catalog_id]['configured_collection_count'] == len(loaded['collections'])

        assert eo.get_catalog()['id'] == config['default_catalog']

    def test_unknown_catalog_raises(self):
        unknown_id = 'not-' + '-'.join(catalogs.get_config()['catalogs'])
        with pytest.raises(ValueError, match='Unknown catalog'):
            eo.get_catalog(unknown_id)


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

    def test_out_of_range_latitude(self):
        with pytest.raises(ValueError, match='Latitudes'):
            eo.search_scenes(bbox=[0, -91, 10, 10])

    def test_no_collections_raises(self):
        with pytest.raises(ValueError, match='explicit `collections`'):
            eo.search_scenes(bbox=[0, 0, 1, 1], collections=[])

    def test_empty_collection_id_raises(self):
        with pytest.raises(ValueError, match='must not be empty'):
            eo.get_collection_details('   ')

    def test_query_kwargs_forward_explicit_filters(self):
        kwargs = eo._query_kwargs(
            targets=['no2-monthly'],
            bbox=(-51.35, -30.25, -51.0, -29.85),
            datetime_range='2020-01-01/2020-12-31',
            max_cloud_cover=20,
            page_limit=10,
            max_items=10,
        )
        assert kwargs['bbox'] == [-51.35, -30.25, -51.0, -29.85]
        assert kwargs['datetime'] == '2020-01-01/2020-12-31'
        assert kwargs['query'] == {'eo:cloud_cover': {'lt': 20.0}}

    def test_query_kwargs_omit_optional_filters(self):
        kwargs = eo._query_kwargs(
            targets=['collection'],
            bbox=(0, 0, 1, 1),
            datetime_range=None,
            max_cloud_cover=None,
            page_limit=1,
            max_items=None,
        )
        assert set(kwargs) == {'collections', 'bbox', 'sortby', 'limit'}


class TestStacHelpers:
    def test_scene_summary_extension_properties(self):
        item = _stac_item()
        item['properties'].update(
            {
                'gsd': 10,
                'sar:polarizations': ['VV'],
                'sar:instrument_mode': 'IW',
                'sat:orbit_state': 'ascending',
                'view:sun_elevation': 40,
                's2:water_percentage': 2,
                'landsat:wrs_path': '001',
                'landsat:wrs_row': '002',
                'naip:state': 'ca',
                'storage:region': 'us-west-2',
            }
        )
        summary = eo._summarize_item(item)
        assert summary['landsat:wrs_path_row'] == '001/002'
        assert summary['sar:polarizations'] == ['VV']
        assert summary['storage:region'] == 'us-west-2'

        item['properties'].pop('landsat:wrs_path')
        assert 'landsat:wrs_path_row' not in eo._summarize_item(item)

    def test_storage_projection_and_s3_helpers(self):
        scheme_item = {
            'properties': {
                'storage:schemes': {
                    'aws': {
                        'bucket': 'bucket',
                        'region': 'eu-west-1',
                        'requester_pays': True,
                    }
                }
            }
        }
        assert eo._storage_info(scheme_item) == {
            'bucket': 'bucket',
            'region': 'eu-west-1',
            'requester_pays': True,
        }
        fallback = eo._storage_info(
            {
                'properties': {
                    'storage:schemes': {'invalid': 'value'},
                    'storage:region': 'us-east-1',
                    'storage:requester_pays': True,
                }
            }
        )
        assert fallback['region'] == 'us-east-1'
        assert fallback['requester_pays'] is True
        assert eo._item_epsg({'properties': {'proj:code': 'EPSG:not-a-number'}}) is None
        assert eo._item_epsg({'assets': {'data': {'proj:epsg': 3857}}}) == 3857

    def test_asset_selection_filters_and_caps(self):
        item = _stac_item()
        item['assets'] = {
            'alternate': {'href': 'ftp://example.com/data.bin', 'roles': ['data']},
            'empty': {'href': '', 'roles': ['data']},
            'metadata': {
                'href': 'https://example.com/metadata.xml',
                'roles': ['metadata'],
            },
            'second': {'href': 'https://example.com/second.tif', 'roles': ['data']},
            'cog_default': {
                'href': 'https://example.com/default.tif',
                'roles': ['data'],
            },
        }
        assert eo._pick_asset_urls(item, max_assets=1) == [
            ('cog_default', 'https://example.com/default.tif', None)
        ]
        assert [key for key, _, _ in eo._pick_asset_urls(item)] == [
            'cog_default',
            'alternate',
            'second',
        ]

    def test_band_collection_and_sparse_spectral_entries(self):
        item = _stac_item()
        item['assets']['unnamed'] = {
            'href': 'https://example.com/unnamed.tif',
            'roles': ['data'],
            'eo:bands': [{}],
        }
        bands = eo._collect_bands([item])
        assert any(band['name'] == 'unnamed' for band in bands)
        assert eo._spectral_entries([{}, {'name': 'plain'}]) == [
            {'@type': 'geocr:SpectralBand', 'name': 'plain'}
        ]


class TestCatalogConfigOverride:
    def test_env_override(self, tmp_path, monkeypatch):
        override = tmp_path / 'custom.yaml'
        override.write_text(
            'catalogs:\n'
            '  my-catalog:\n'
            '    url: https://example.com/stac\n'
            '    collections: ["coll-a"]\n',
            encoding='utf-8',
        )
        monkeypatch.setenv(catalogs.CONFIG_ENV_VAR, str(override))
        catalogs.reload_config()
        try:
            assert list(catalogs.get_config()['catalogs']) == ['my-catalog']
            assert catalogs.get_catalog()['collections'] == ['coll-a']
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

    @pytest.mark.parametrize(
        ('yaml_content', 'message'),
        [
            ('- catalog\n', 'YAML mapping'),
            ('{}\n', 'non-empty `catalogs` mapping'),
            ('catalogs:\n  entry: text\n', 'missing a `url`'),
            ('catalogs:\n  "":\n    url: https://example.com\n', 'must not be empty'),
            (
                'catalogs:\n  entry:\n    url: https://example.com\n    collections: value\n',
                'collections must be a list',
            ),
            (
                'catalogs:\n  entry:\n    url: https://example.com\n    collections: [""]\n',
                'non-empty strings',
            ),
            (
                'catalogs:\n  entry:\n    url: https://example.com\n    collections: [same, same]\n',
                'must be unique',
            ),
            (
                'default_catalog: absent\ncatalogs:\n  entry:\n    url: https://example.com\n',
                'is not defined',
            ),
        ],
    )
    def test_registry_validation(self, tmp_path, monkeypatch, yaml_content, message):
        override = tmp_path / 'catalogs.yaml'
        override.write_text(yaml_content, encoding='utf-8')
        monkeypatch.setenv(catalogs.CONFIG_ENV_VAR, str(override))
        catalogs.reload_config()
        try:
            with pytest.raises(ValueError, match=message):
                catalogs.get_config()
        finally:
            catalogs.reload_config()

    def test_registry_defaults_and_normalizes_ids(self, tmp_path, monkeypatch):
        override = tmp_path / 'catalogs.yaml'
        override.write_text(
            'catalogs:\n  Mixed-Case:\n    url: https://example.com\n',
            encoding='utf-8',
        )
        monkeypatch.setenv(catalogs.CONFIG_ENV_VAR, str(override))
        catalogs.reload_config()
        try:
            config = catalogs.get_config()
            assert config['default_catalog'] == 'mixed-case'
            assert catalogs.get_catalog()['name'] == 'Mixed-Case'
            assert catalogs.get_catalog()['description'] == ''
            assert catalogs.get_catalog()['collections'] == []
        finally:
            catalogs.reload_config()


class TestGeocroissantFromStac:
    def _build(self, items, **kwargs):
        return eo.geocroissant_from_stac(
            name='Test EO Dataset',
            description='Generated from pystac model instances.',
            license_url='https://creativecommons.org/licenses/by/4.0/',
            creators=['NASA'],
            raw_items=items,
            **kwargs,
        )

    def test_empty_items_raise(self):
        with pytest.raises(ValueError, match='No STAC scenes'):
            self._build([])

    def test_document_structure_and_validation(self):
        doc = self._build([_stac_item(), _stac_item('S2_20230801', dt='2023-08-01T18:55:31Z')])
        assert doc['conformsTo'] == [
            'http://mlcommons.org/croissant/1.1',
            'http://mlcommons.org/croissant/geo/1.0',
        ]
        assert 'geocr:spatialBias' not in doc
        assert 'rai:dataLimitations' not in doc
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
        # Distribution: every usable asset for every returned scene.
        assert len(doc['distribution']) == 10
        assert all(d['contentUrl'].startswith('https://') for d in doc['distribution'])
        # RecordSet: inline rows keyed exactly like field ids.
        rs = doc['recordSet'][0]
        field_ids = {f['@id'] for f in rs['field']}
        assert field_ids == {
            f'scenes/{n}'
            for n in (
                'scene_id',
                'collection',
                'datetime',
                'cloud_cover',
                'epsg',
                'image_url',
                'asset_urls',
            )
        }
        assert len(rs['data']) == 2
        row = rs['data'][0]
        assert set(row.keys()) == field_ids
        assert row['scenes/scene_id'] == 'S2_20230715'
        assert row['scenes/cloud_cover'] == 12.5
        assert row['scenes/epsg'] == 32610
        assert row['scenes/image_url'].endswith('B02.tif')
        assert len(row['scenes/asset_urls']) == 5
        # The generated document must pass metadata validation offline.
        dataset = common.load_dataset(doc)
        assert dataset.metadata.name == 'Test EO Dataset'

    def test_document_with_rai_properties(self):
        doc = self._build(
            [_stac_item()],
            spatial_bias='Regional coverage',
            sampling_strategy='Uniform 10-day intervals',
            data_collection='Sentinel-2 L2A STAC query',
            personal_sensitive_information=['No PII'],
            data_limitations=['Atmospheric occlusion'],
            data_biases=['Cloud-free bias'],
            data_use_cases=['Flood mapping'],
            data_social_impact='Emergency response aid',
            has_synthetic_data=False,
            rai_properties={'annotatorDemographics': ['Domain experts'], 'prov:wasGeneratedBy': 'Automated STAC harvest'},
        )
        assert 'http://mlcommons.org/croissant/RAI/1.0' in doc['conformsTo']
        assert doc['geocr:spatialBias'] == 'Regional coverage'
        assert doc['geocr:samplingStrategy'] == 'Uniform 10-day intervals'
        assert doc['rai:dataCollection'] == 'Sentinel-2 L2A STAC query'
        assert doc['rai:personalSensitiveInformation'] == ['No PII']
        assert doc['rai:dataLimitations'] == ['Atmospheric occlusion']
        assert doc['rai:dataBiases'] == ['Cloud-free bias']
        assert doc['rai:dataUseCases'] == ['Flood mapping']
        assert doc['rai:dataSocialImpact'] == 'Emergency response aid'
        assert doc['rai:hasSyntheticData'] is False
        assert doc['rai:annotatorDemographics'] == ['Domain experts']
        assert doc['prov:wasGeneratedBy'] == 'Automated STAC harvest'

    def test_field_band_configuration_attached_to_image_url(self):
        doc = self._build([_stac_item()])
        image_field = next(
            field for field in doc['recordSet'][0]['field'] if field['@id'] == 'scenes/image_url'
        )
        assert image_field['@id'] == 'scenes/image_url'
        assert image_field['geocr:bandConfiguration']['geocr:totalBands'] == 4

    def test_veda_interval_item_metadata(self):
        doc = eo.geocroissant_from_stac(
            name='VEDA NO2',
            description='Monthly nitrogen dioxide.',
            license_url='',
            creators=['NASA'],
            raw_items=[_veda_stac_item()],
            catalog_id='veda',
        )

        assert doc['geocr:recordEndpoint'] == 'https://openveda.cloud/api/stac'
        assert doc['temporalCoverage'] == '2020-01-01/2020-01-31'
        assert doc['geocr:bandConfiguration']['geocr:bandNamesList'] == ['NO2']
        row = doc['recordSet'][0]['data'][0]
        assert row['scenes/datetime'] == '2020-01-01T00:00:00Z'
        assert row['scenes/epsg'] == 4326
        assert row['scenes/image_url'] == 's3://veda-data-store/no2/2020-01.tif'
        assert doc['distribution'][0]['contentUrl'] == (
            's3://veda-data-store/no2/2020-01.tif'
        )

    def test_sparse_item_and_optional_metadata(self):
        item = _stac_item(item_id='sparse')
        item.pop('bbox')
        item.pop('collection')
        item['properties'] = {}
        item['assets'] = {
            'metadata': {
                'href': 'https://example.com/metadata.json',
                'roles': ['metadata'],
            }
        }
        document = eo.geocroissant_from_stac(
            name='Sparse',
            description='',
            license_url='',
            creators=None,
            cite_as='Sparse citation',
            raw_items=[item],
        )
        assert document['citeAs'] == 'Sparse citation'
        assert 'description' not in document
        assert 'license' not in document
        assert 'creator' not in document
        assert 'spatialCoverage' not in document
        assert 'temporalCoverage' not in document
        assert 'geocr:bandConfiguration' not in document
        assert 'distribution' not in document
        row = document['recordSet'][0]['data'][0]
        assert row['scenes/cloud_cover'] == ''
        assert row['scenes/epsg'] == ''
        assert row['scenes/image_url'] == ''
        assert row['scenes/asset_urls'] == []

    def test_raster_scale_storage_and_distribution_cap(self):
        item = _stac_item()
        item['assets']['extra'] = {
            'href': 'https://example.com/extra.tif',
            'roles': ['data'],
        }
        item['properties']['storage:schemes'] = {
            'aws': {'bucket': 'bucket', 'region': 'us-west-2', 'requester_pays': True}
        }
        for index, asset in enumerate(item['assets'].values()):
            asset['file:size'] = index + 1
            asset['raster:bands'] = [{'scale': 0.01, 'offset': -1 if index else None}]
        document = eo.geocroissant_from_stac(
            name='Scaled',
            description='Scaled raster data.',
            license_url='',
            creators=[],
            raw_items=[item],
            max_distribution_assets=1,
        )
        properties = {entry['name']: entry['value'] for entry in document['additionalProperty']}
        assert properties['storageRequesterPays(collections)'] == [item['collection']]
        assert properties['reflectanceConversion(DN*scale+offset)']
        assert len(document['distribution']) == 1
        assert document['distribution'][0]['contentSize']
