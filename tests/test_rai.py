"""Tests for Responsible AI (RAI) and GeoCroissant RAI properties."""

import pytest
from geocr_mcp_server import common, reference, spec
from geocr_mcp_server.tools import GeoCroissantTools
from mcp.server.fastmcp import Context
from unittest.mock import AsyncMock


def test_build_scaffold_with_rai():
    """Verifies build_scaffold properly serializes RAI fields and conformance."""
    doc = spec.build_scaffold(
        name='Weather Forecast Discussion RAI',
        description='Benchmark pairing HRRR grids with SPC forecast discussions.',
        license='https://creativecommons.org/licenses/by/4.0/',
        cite_as='Example citation',
        version='1.0.0',
        spatial_bias='Contiguous United States (CONUS) HRRR grid domain.',
        sampling_strategy='Daily 07Z HRRR 3km surface forecast grids paired with SPC outlooks.',
        data_collection='Aggregated from NOAA NCEI HRRR archives and NWS SPC text archives.',
        data_collection_type=['Direct measurement', 'Web API'],
        data_collection_missing_data='None reported.',
        data_collection_raw_data='Raw GRIB2 files from NOAA NCEI.',
        data_imputation_protocol='No imputation performed on missing values.',
        data_preprocessing_protocol=['Bilinear interpolation to 3km grid.'],
        data_manipulation_protocol='GRIB2 to NetCDF format conversion.',
        data_annotation_protocol=['Operational meteorologist peer review.'],
        data_annotation_platform=['NWS AWIPS II workstations.'],
        data_annotation_analysis=['Standardized synoptic weather classification.'],
        annotations_per_item='1 forecaster discussion per forecast cycle.',
        annotator_demographics=['NOAA NWS Storm Prediction Center operational meteorologists.'],
        machine_annotation_tools=['Automated severe hail verification algorithms.'],
        data_biases=['Geographically constrained to CONUS.'],
        data_limitations=['HRRR subset includes 9 selected surface/atmospheric variable layers.'],
        data_use_cases=['Multimodal weather modeling, severe convective storm prediction.'],
        data_social_impact='Advances early severe weather detection and automated warnings.',
        personal_sensitive_information=[
            'Contains no personal sensitive information; strictly public observations.'
        ],
        data_release_maintenance_plan='Annual updates aligned with SPC operational seasons.',
        has_synthetic_data=False,
    )

    # 1. Conformance & Context
    assert spec.RAI_CONFORMANCE in doc['conformsTo']
    assert spec.CROISSANT_CONFORMANCE in doc['conformsTo']
    assert spec.GEO_CONFORMANCE in doc['conformsTo']
    assert doc['@context']['rai'] == spec.RAI_NAMESPACE

    # 2. GeoCroissant RAI
    assert doc['geocr:spatialBias'] == 'Contiguous United States (CONUS) HRRR grid domain.'
    assert 'Daily 07Z' in doc['geocr:samplingStrategy']

    # 3. Core Croissant RAI
    assert (
        doc['rai:dataCollection']
        == 'Aggregated from NOAA NCEI HRRR archives and NWS SPC text archives.'
    )
    assert doc['rai:dataCollectionType'] == ['Direct measurement', 'Web API']
    assert doc['rai:dataBiases'] == ['Geographically constrained to CONUS.']
    assert doc['rai:dataLimitations'] == [
        'HRRR subset includes 9 selected surface/atmospheric variable layers.'
    ]
    assert doc['rai:personalSensitiveInformation'] == [
        'Contains no personal sensitive information; strictly public observations.'
    ]
    assert doc['rai:hasSyntheticData'] is False

    # 4. mlcroissant Validation & Parsing
    dataset = common.load_dataset(doc)
    assert dataset.metadata.name == 'Weather Forecast Discussion RAI'
    assert dataset.metadata.spatial_bias == 'Contiguous United States (CONUS) HRRR grid domain.'
    assert dataset.metadata.data_biases == ['Geographically constrained to CONUS.']
    assert dataset.metadata.data_limitations == [
        'HRRR subset includes 9 selected surface/atmospheric variable layers.'
    ]


def test_inspect_geocroissant_extracts_rai():
    """Verifies common.summarize_croissant creates a structured responsible_ai section."""
    doc = spec.build_scaffold(
        name='RAI Inspection Test',
        spatial_bias='Spatially limited to Amazon basin.',
        sampling_strategy='Randomized stratified sampling by cloud cover.',
        data_biases=['Deforestation imagery biased toward dry season acquisitions.'],
        data_limitations=['Wet season images obscured by convective clouds.'],
        data_use_cases=['Forest loss segmentation'],
        data_social_impact='Enables community monitoring of tropical deforestation.',
        personal_sensitive_information=['Contains no personal sensitive information.'],
        has_synthetic_data=False,
    )

    dataset = common.load_dataset(doc)
    summary = common.summarize_metadata(dataset.metadata)

    assert 'responsible_ai' in summary
    rai_summary = summary['responsible_ai']
    assert rai_summary['spatialBias'] == 'Spatially limited to Amazon basin.'
    assert rai_summary['samplingStrategy'] == 'Randomized stratified sampling by cloud cover.'
    assert rai_summary['dataBiases'] == [
        'Deforestation imagery biased toward dry season acquisitions.'
    ]
    assert rai_summary['dataLimitations'] == ['Wet season images obscured by convective clouds.']
    assert rai_summary['dataUseCases'] == ['Forest loss segmentation']
    assert (
        rai_summary['dataSocialImpact']
        == 'Enables community monitoring of tropical deforestation.'
    )
    assert rai_summary['personalSensitiveInformation'] == [
        'Contains no personal sensitive information.'
    ]
    assert rai_summary['hasSyntheticData'] is False


def test_reference_rai_topic():
    """Verifies get_geocroissant_spec_reference with topic='rai' returns full documentation."""
    rai_ref = reference.render_reference('rai')
    assert 'Responsible AI (RAI) Specification Reference' in rai_ref
    assert 'rai:dataBiases' in rai_ref
    assert 'rai:dataLimitations' in rai_ref
    assert 'geocr:spatialBias' in rai_ref
    assert 'geocr:samplingStrategy' in rai_ref
    assert 'rai:personalSensitiveInformation' in rai_ref
    assert 'rai:hasSyntheticData' in rai_ref

    all_ref = reference.render_reference('all')
    assert 'Responsible AI (RAI) Specification Reference' in all_ref


@pytest.mark.asyncio
async def test_tools_create_geocroissant_scaffold_with_rai():
    """Verifies create_geocroissant_scaffold tool accepts RAI parameters and validates cleanly."""
    tools = GeoCroissantTools()
    mock_ctx = AsyncMock(spec=Context)

    result = await tools.create_geocroissant_scaffold(
        ctx=mock_ctx,
        name='Scaffolded RAI Dataset',
        description='Dataset with Responsible AI metadata.',
        license='https://creativecommons.org/licenses/by/4.0/',
        spatial_bias='Global coverage limited to latitudes 60N to 60S.',
        sampling_strategy='Systematic grid sampling every 10km.',
        data_biases=['Polar regions omitted due to orbit inclination.'],
        data_limitations=['Low light performance degraded in winter months.'],
        data_use_cases=['Global vegetation index monitoring'],
        data_social_impact='Informs global food security early warning systems.',
        personal_sensitive_information=['Contains no PII.'],
    )

    assert result.valid is True
    assert result.errors == []
    assert (
        result.json_ld['geocr:spatialBias'] == 'Global coverage limited to latitudes 60N to 60S.'
    )
    assert result.json_ld['rai:dataBiases'] == ['Polar regions omitted due to orbit inclination.']
    assert spec.RAI_CONFORMANCE in result.json_ld['conformsTo']


@pytest.mark.asyncio
async def test_jefferson_parish_hurricane_ida_rai_scenario():
    """Validates the exact hackweek scenario for Jefferson Parish Hurricane Ida with RAI disclosures."""
    tools = GeoCroissantTools()
    mock_ctx = AsyncMock(spec=Context)

    result = await tools.create_geocroissant_scaffold(
        ctx=mock_ctx,
        name='Hurricane-Ida-Jefferson-Parish-Damage-Assessment',
        description='Dual optical and radar imagery for blue-tarp and flood damage around Jefferson Parish, LA.',
        license='https://creativecommons.org/licenses/by/4.0/',
        bbox=[-90.3, 29.8, -89.9, 30.1],
        spatial_bias='Constrained to Jefferson Parish, Louisiana (coastal bayous and metropolitan New Orleans fringe).',
        sampling_strategy='Filtered Sentinel-2 (<20% cloud cover) and Sentinel-1 GRD scenes between Aug 23 and Sep 26, 2021.',
        data_biases=[
            'Optical observations biased toward post-storm cloud-free days; peak hurricane hours omitted.'
        ],
        data_limitations=[
            'Immediate post-landfall cloud cover obscures blue-tarp rooftops on Aug 29-31.',
            'Specular SAR backscatter from marsh wetlands may be conflated with structural standing water.',
        ],
        data_social_impact='Accelerates FEMA and local emergency response while avoiding biased relief resource allocation.',
        personal_sensitive_information=[
            'Contains only open Earth observation satellite rasters; no personal identifiable data.'
        ],
        has_synthetic_data=False,
        rai_properties={
            'prov:wasGeneratedBy': 'Copernicus Sentinel-1 and Sentinel-2 Missions / ESA Processing Baseline',
        },
    )

    assert result.valid is True
    assert result.errors == []
    json_ld = result.json_ld
    assert (
        json_ld['geocr:spatialBias']
        == 'Constrained to Jefferson Parish, Louisiana (coastal bayous and metropolitan New Orleans fringe).'
    )
    assert len(json_ld['rai:dataLimitations']) == 2
    assert json_ld['rai:hasSyntheticData'] is False
    assert (
        json_ld['prov:wasGeneratedBy']
        == 'Copernicus Sentinel-1 and Sentinel-2 Missions / ESA Processing Baseline'
    )
    assert spec.RAI_CONFORMANCE in json_ld['conformsTo']

    # Test inspection through common.summarize_metadata
    ds = common.load_dataset(json_ld)
    summary = common.summarize_metadata(ds.metadata)
    rai_summary = summary.get('responsible_ai', {})
    assert rai_summary['spatialBias'] == json_ld['geocr:spatialBias']
    assert rai_summary['dataBiases'] == json_ld['rai:dataBiases']
    assert rai_summary['dataSocialImpact'] == json_ld['rai:dataSocialImpact']
    assert rai_summary['hasSyntheticData'] is False


def test_rai_properties_with_none_values():
    """Verifies that None values in rai_properties are safely ignored."""
    doc = spec.build_scaffold(
        name='None test',
        rai_properties={'val_none': None, 'custom': 'abc'},
    )
    assert doc['rai:custom'] == 'abc'
    assert 'rai:val_none' not in doc

    item = {
        'id': 'item1',
        'type': 'Feature',
        'geometry': {
            'type': 'Polygon',
            'coordinates': [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
        },
        'bbox': [0, 0, 1, 1],
        'properties': {'datetime': '2020-01-01T00:00:00Z'},
        'assets': {'data': {'href': 'https://example.com/data.tif', 'type': 'image/tiff'}},
    }
    from geocr_mcp_server import eo

    eo_doc = eo.geocroissant_from_stac(
        name='EO None test',
        description='EO desc',
        license_url='https://creativecommons.org/licenses/by/4.0/',
        creators=['NASA'],
        raw_items=[item],
        rai_properties={'val_none': None, 'custom': 'xyz'},
    )
    assert eo_doc['rai:custom'] == 'xyz'
    assert 'rai:val_none' not in eo_doc


def test_summarize_rai_and_record_set_synthetic_coverage():
    """Verifies synthetic data extraction across record sets, dict metadata, and extra properties."""
    import types
    from typing import Any, cast

    # 1. summarize_record_set with has_synthetic_data attribute
    rs1 = types.SimpleNamespace(
        uuid='rs1',
        name='rs1',
        id='rs1',
        description='test',
        has_synthetic_data=True,
        key=None,
        data=None,
        fields=[],
    )
    res1 = common.summarize_record_set(cast(Any, rs1))
    assert res1['hasSyntheticData'] is True

    # 2. summarize_record_set with extra_properties
    rs2 = types.SimpleNamespace(
        uuid='rs2',
        name='rs2',
        id='rs2',
        description='test',
        key=None,
        data=None,
        fields=[],
        extra_properties={'hasSyntheticData': False},
    )
    res2 = common.summarize_record_set(cast(Any, rs2))
    assert res2['hasSyntheticData'] is False

    rs3 = types.SimpleNamespace(
        uuid='rs3',
        name='rs3',
        id='rs3',
        description='test',
        key=None,
        data=None,
        fields=[],
        extra_properties={'rai:hasSyntheticData': True},
    )
    res3 = common.summarize_record_set(cast(Any, rs3))
    assert res3['hasSyntheticData'] is True


    # 3. summarize_rai_metadata with dict
    res_dict1 = common.summarize_rai_metadata({'rai:hasSyntheticData': True})
    assert res_dict1['hasSyntheticData'] is True

    res_dict2 = common.summarize_rai_metadata({'hasSyntheticData': False})
    assert res_dict2['hasSyntheticData'] is False

    # 4. summarize_rai_metadata with extra_properties
    meta_ns = types.SimpleNamespace(extra_properties={'hasSyntheticData': True})
    res_meta = common.summarize_rai_metadata(meta_ns)
    assert res_meta['hasSyntheticData'] is True

    meta_ns2 = types.SimpleNamespace(extra_properties={'rai:hasSyntheticData': False})
    res_meta2 = common.summarize_rai_metadata(meta_ns2)
    assert res_meta2['hasSyntheticData'] is False
