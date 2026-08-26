"""GeoCroissant JSON-LD scaffold generation.

The vocabulary constants follow `docs/croissant-geo-spec.md`. The tool layer
validates generated documents with the configured ``mlcroissant`` package.
"""

from typing import Any, Sequence


CROISSANT_CONFORMANCE = 'http://mlcommons.org/croissant/1.1'
GEO_CONFORMANCE = 'http://mlcommons.org/croissant/geo/1.0'
GEO_NAMESPACE = 'http://mlcommons.org/croissant/geo/'
RAI_CONFORMANCE = 'http://mlcommons.org/croissant/RAI/1.0'
RAI_NAMESPACE = 'http://mlcommons.org/croissant/RAI/'


def official_context() -> dict[str, Any]:
    """Returns the Croissant @context used by the server, extended with `geocr` and `rai`."""
    return {
        '@language': 'en',
        '@vocab': 'https://schema.org/',
        'cr': 'http://mlcommons.org/croissant/',
        'dct': 'http://purl.org/dc/terms/',
        'geocr': GEO_NAMESPACE,
        'rai': RAI_NAMESPACE,
        'prov': 'http://www.w3.org/ns/prov#',
        'sc': 'https://schema.org/',
        'citeAs': 'cr:citeAs',
        'column': 'cr:column',
        'conformsTo': 'dct:conformsTo',
        'data': {'@id': 'cr:data', '@type': '@json'},
        'dataType': {'@id': 'cr:dataType', '@type': '@vocab'},
        'examples': {'@id': 'cr:examples', '@type': '@json'},
        'extract': 'cr:extract',
        'field': 'cr:field',
        'fileProperty': 'cr:fileProperty',
        'fileObject': 'cr:fileObject',
        'fileSet': 'cr:fileSet',
        'format': 'cr:format',
        'includes': 'cr:includes',
        'isLiveDataset': 'cr:isLiveDataset',
        'jsonPath': 'cr:jsonPath',
        'key': 'cr:key',
        'md5': 'cr:md5',
        'parentField': 'cr:parentField',
        'path': 'cr:path',
        'recordSet': 'cr:recordSet',
        'references': 'cr:references',
        'regex': 'cr:regex',
        'repeated': 'cr:repeated',
        'replace': 'cr:replace',
        'separator': 'cr:separator',
        'source': 'cr:source',
        'subField': 'cr:subField',
        'transform': 'cr:transform',
        'containedIn': {'@id': 'cr:containedIn', '@type': '@id'},
        'isArray': 'cr:isArray',
        'arrayShape': 'cr:arrayShape',
    }


def _quantitative(value: Any, unit: str | None) -> dict[str, Any]:
    entry: dict[str, Any] = {'@type': 'QuantitativeValue', 'value': value}
    if unit:
        entry['unitText'] = unit
    return entry


def build_scaffold(
    *,
    name: str,
    description: str = '',
    license: str = '',
    version: str = '',
    date_published: str = '',
    creators: list[str] | None = None,
    bbox: list[float] | str | None = None,
    temporal_coverage: str | None = None,
    coordinate_reference_system: str = '',
    spatial_resolution: float | int | None = None,
    spatial_resolution_unit: str = 'm',
    temporal_resolution_value: float | int | None = None,
    temporal_resolution_unit: str = 'days',
    band_names: list[str] | None = None,
    spectral_bands: list[dict[str, Any]] | None = None,
    file_sets: list[dict[str, Any]] | None = None,
    file_objects: list[dict[str, Any]] | None = None,
    record_set_name: str | None = 'records',
    record_set_description: str = '',
    field_name: str = 'data',
    field_data_type: str = 'sc:ImageObject',
    field_is_array: bool = False,
    field_array_shape: str | None = None,
    source_file_set_id: str | None = None,
    cite_as: str = '',
    # --- Responsible AI (GeoCroissant & Croissant RAI) ---
    spatial_bias: str = '',
    sampling_strategy: str = '',
    data_collection: str = '',
    data_collection_type: list[str] | None = None,
    data_collection_missing_data: str = '',
    data_collection_raw_data: str = '',
    data_collection_timeframe: list[str] | None = None,
    data_imputation_protocol: str = '',
    data_preprocessing_protocol: list[str] | None = None,
    data_manipulation_protocol: str = '',
    data_annotation_protocol: list[str] | None = None,
    data_annotation_platform: list[str] | None = None,
    data_annotation_analysis: list[str] | None = None,
    annotations_per_item: str = '',
    annotator_demographics: list[str] | None = None,
    machine_annotation_tools: list[str] | None = None,
    data_biases: list[str] | None = None,
    data_limitations: list[str] | None = None,
    data_use_cases: list[str] | None = None,
    data_social_impact: str = '',
    personal_sensitive_information: list[str] | None = None,
    data_release_maintenance_plan: str = '',
    has_synthetic_data: bool | None = None,
    rai_properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Builds a GeoCroissant JSON-LD document from structured parameters.

    The output follows the HLS Burn Scars example in the GeoCroissant
    specification. The tool layer validates it after generation.

    Bounding boxes use the standard GIS order [min_lon, min_lat, max_lon,
    max_lat]; they are serialized into the schema.org GeoShape `box` ordering
    ("minLat minLon maxLat maxLon") required by the specification.
    """
    if not name or not name.strip():
        raise ValueError('Parameter `name` is required and must not be empty.')
    if field_array_shape and not field_is_array:
        raise ValueError(
            '`field_array_shape` requires `field_is_array=True` '
            '(per spec: isArray must be true when arrayShape is set).'
        )

    doc: dict[str, Any] = {
        '@context': official_context(),
        '@type': 'Dataset',
        'name': name.strip(),
        'conformsTo': [CROISSANT_CONFORMANCE, GEO_CONFORMANCE],
    }
    if description:
        doc['description'] = description
    if license:
        doc['license'] = license
    if cite_as:
        doc['citeAs'] = cite_as
    if version:
        doc['version'] = version
    if date_published:
        doc['datePublished'] = date_published
    if creators:
        doc['creator'] = [{'@type': 'Organization', 'name': creator} for creator in creators]

    # --- schema.org coverage ---
    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = _parse_bbox(bbox)
        doc['spatialCoverage'] = {
            '@type': 'Place',
            'geo': {
                '@type': 'GeoShape',
                # Spec-required ordering: "minLat minLon maxLat maxLon".
                'box': f'{min_lat} {min_lon} {max_lat} {max_lon}',
            },
        }
    if temporal_coverage:
        doc['temporalCoverage'] = temporal_coverage

    # --- GeoCroissant dataset-level properties ---
    if coordinate_reference_system:
        doc['geocr:coordinateReferenceSystem'] = coordinate_reference_system
    if spatial_resolution is not None:
        doc['geocr:spatialResolution'] = _quantitative(spatial_resolution, spatial_resolution_unit)
    if temporal_resolution_value is not None:
        doc['geocr:temporalResolution'] = _quantitative(
            temporal_resolution_value, temporal_resolution_unit
        )
    band_names = band_names or []
    if band_names:
        doc['geocr:bandConfiguration'] = _band_configuration(band_names)
    if spectral_bands:
        doc['geocr:spectralBandMetadata'] = [_spectral_band(band) for band in spectral_bands]

    # --- Responsible AI (GeoCroissant & Croissant RAI) ---
    has_rai = False
    if spatial_bias:
        doc['geocr:spatialBias'] = spatial_bias
        has_rai = True
    if sampling_strategy:
        doc['geocr:samplingStrategy'] = sampling_strategy
        has_rai = True
    if has_synthetic_data is not None:
        doc['rai:hasSyntheticData'] = has_synthetic_data
        has_rai = True

    rai_fields_map = [
        ('rai:dataCollection', data_collection),
        ('rai:dataCollectionType', data_collection_type),
        ('rai:dataCollectionMissingData', data_collection_missing_data),
        ('rai:dataCollectionRawData', data_collection_raw_data),
        ('rai:dataCollectionTimeFrame', data_collection_timeframe),
        ('rai:dataImputationProtocol', data_imputation_protocol),
        ('rai:dataPreprocessingProtocol', data_preprocessing_protocol),
        ('rai:dataDataManipulationProtocol', data_manipulation_protocol),
        ('rai:dataAnnotationProtocol', data_annotation_protocol),
        ('rai:dataAnnotationPlatform', data_annotation_platform),
        ('rai:dataAnnotationAnalysis', data_annotation_analysis),
        ('rai:annotationsPerItem', annotations_per_item),
        ('rai:annotatorDemographics', annotator_demographics),
        ('rai:machineAnnotationTools', machine_annotation_tools),
        ('rai:dataBiases', data_biases),
        ('rai:dataLimitations', data_limitations),
        ('rai:dataUseCases', data_use_cases),
        ('rai:dataSocialImpact', data_social_impact),
        ('rai:personalSensitiveInformation', personal_sensitive_information),
        ('rai:dataReleaseMaintenancePlan', data_release_maintenance_plan),
    ]
    for json_key, val in rai_fields_map:
        if val:
            doc[json_key] = val
            has_rai = True

    if rai_properties:
        for k, val in rai_properties.items():
            if val is not None:
                key = k if (':' in k or k.startswith('@')) else f'rai:{k}'
                doc[key] = val
                has_rai = True

    if has_rai and RAI_CONFORMANCE not in doc['conformsTo']:
        doc['conformsTo'].append(RAI_CONFORMANCE)

    # --- Distribution ---
    distribution: list[dict[str, Any]] = []
    distribution_ids: list[str] = []
    for i, fs in enumerate(file_sets or []):
        fs_id = str(fs.get('id') or fs.get('name') or f'fileset_{i + 1}')
        entry: dict[str, Any] = {
            '@type': 'cr:FileSet',
            '@id': fs_id,
            'name': str(fs.get('name') or fs_id),
            'encodingFormat': fs.get('encoding_format') or 'application/octet-stream',
            'includes': fs.get('includes') or '**/*',
        }
        if fs.get('description'):
            entry['description'] = fs['description']
        if fs.get('contained_in'):
            entry['containedIn'] = {'@id': fs['contained_in']}
        distribution.append(entry)
        distribution_ids.append(fs_id)
    for i, fo in enumerate(file_objects or []):
        fo_id = str(fo.get('id') or fo.get('name') or f'fileobject_{i + 1}')
        content_url = fo.get('content_url')
        if not content_url and not fo.get('contained_in'):
            raise ValueError(
                f'FileObject "{fo_id}" is missing `content_url` '
                '(mandatory unless declared inside a container via contained_in).'
            )
        entry = {
            '@type': 'cr:FileObject',
            '@id': fo_id,
            'name': str(fo.get('name') or fo_id),
            'encodingFormat': fo.get('encoding_format') or 'application/octet-stream',
        }
        if content_url:
            entry['contentUrl'] = str(content_url)
        if fo.get('sha256'):
            entry['sha256'] = fo['sha256']
        if fo.get('md5'):
            entry['md5'] = fo['md5']
        if fo.get('description'):
            entry['description'] = fo['description']
        if fo.get('contained_in'):
            entry['containedIn'] = {'@id': fo['contained_in']}
        distribution.append(entry)
        distribution_ids.append(fo_id)
    if distribution:
        doc['distribution'] = distribution

    # --- RecordSet wired to the distribution ---
    if record_set_name:
        doc['recordSet'] = [
            _build_record_set(
                record_set_name=record_set_name,
                record_set_description=record_set_description,
                field_name=field_name,
                field_data_type=field_data_type,
                field_is_array=field_is_array,
                field_array_shape=field_array_shape,
                source_file_set_id=source_file_set_id,
                band_names=band_names,
                distribution=distribution,
                spatial_resolution=spatial_resolution,
                spatial_resolution_unit=spatial_resolution_unit,
                temporal_resolution_value=temporal_resolution_value,
                temporal_resolution_unit=temporal_resolution_unit,
            )
        ]
    return doc


def _band_configuration(band_names: list[str]) -> dict[str, Any]:
    return {
        '@type': 'geocr:BandConfiguration',
        'geocr:totalBands': len(band_names),
        'geocr:bandNamesList': band_names,
    }


def _spectral_band(band: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        '@type': 'geocr:SpectralBand',
        'name': band.get('name'),
    }

    # Center wavelength
    center = band.get('geocr:centerWavelength') or band.get('centerWavelength')
    if isinstance(center, dict):
        if center.get('@type') == 'QuantitativeValue' and 'value' in center:
            entry['geocr:centerWavelength'] = center
        else:
            val = center.get('value')
            unit = center.get('unitText') or center.get('unit', 'nm')
            if val is not None:
                entry['geocr:centerWavelength'] = _quantitative(val, unit)
    elif center is not None:
        entry['geocr:centerWavelength'] = _quantitative(
            center, band.get('centerWavelengthUnit', band.get('unit', 'nm'))
        )
    else:
        center_val = band.get('centerWavelengthValue', band.get('value'))
        center_unit = band.get('centerWavelengthUnit', band.get('unit', 'nm'))
        if center_val is not None:
            entry['geocr:centerWavelength'] = _quantitative(center_val, center_unit)

    # Bandwidth
    width = band.get('geocr:bandwidth') or band.get('bandwidth')
    if isinstance(width, dict):
        if width.get('@type') == 'QuantitativeValue' and 'value' in width:
            entry['geocr:bandwidth'] = width
        else:
            val = width.get('value')
            unit = width.get('unitText') or width.get('unit', 'nm')
            if val is not None:
                entry['geocr:bandwidth'] = _quantitative(val, unit)
    elif width is not None:
        entry['geocr:bandwidth'] = _quantitative(
            width, band.get('bandwidthUnit', band.get('unit', 'nm'))
        )
    else:
        width_val = band.get('bandwidthValue')
        width_unit = band.get('bandwidthUnit')
        if width_val is not None:
            entry['geocr:bandwidth'] = _quantitative(width_val, width_unit)

    return entry



def _build_record_set(
    *,
    record_set_name: str,
    record_set_description: str,
    field_name: str,
    field_data_type: str,
    field_is_array: bool,
    field_array_shape: str | None,
    source_file_set_id: str | None,
    band_names: list[str],
    distribution: list[dict[str, Any]],
    spatial_resolution: float | int | None,
    spatial_resolution_unit: str,
    temporal_resolution_value: float | int | None,
    temporal_resolution_unit: str,
) -> dict[str, Any]:
    rs_id = record_set_name
    field_id = f'{rs_id}/{field_name}'
    field_entry: dict[str, Any] = {
        '@type': 'cr:Field',
        '@id': field_id,
        'name': field_name,
        'dataType': field_data_type,
    }
    if band_names:
        field_entry['geocr:bandConfiguration'] = _band_configuration(band_names)
    if field_is_array:
        field_entry['isArray'] = True
        if field_array_shape:
            field_entry['arrayShape'] = field_array_shape

    source_id = source_file_set_id or (distribution[0]['@id'] if distribution else None)
    matched = next((d for d in distribution if d['@id'] == source_id), None)
    if matched is not None:
        source_key = 'fileSet' if matched['@type'] == 'cr:FileSet' else 'fileObject'
        field_entry['source'] = {
            source_key: {'@id': source_id},
            'extract': {'fileProperty': 'content'},
        }
    else:
        # No matching distribution: fall back to a constant-value field so the
        # RecordSet still validates standalone.
        field_entry.pop('source', None)
        field_entry['value'] = ''
        field_entry.setdefault('dataType', 'sc:Text')

    record_set: dict[str, Any] = {
        '@type': 'cr:RecordSet',
        '@id': rs_id,
        'name': record_set_description or rs_id,
        'key': {'@id': field_id},
        'field': [field_entry],
    }
    if spatial_resolution is not None:
        record_set['geocr:spatialResolution'] = _quantitative(
            spatial_resolution, spatial_resolution_unit
        )
    if temporal_resolution_value is not None:
        record_set['geocr:temporalResolution'] = _quantitative(
            temporal_resolution_value, temporal_resolution_unit
        )
    return record_set


def _parse_bbox(bbox: Sequence[float | int] | str) -> tuple[float, float, float, float]:
    """Parses [min_lon, min_lat, max_lon, max_lat] into a lon/lat quartet."""
    if isinstance(bbox, str):
        parts = [p.strip() for p in bbox.split(',')]
        if len(parts) != 4:
            raise ValueError('bbox string must contain exactly 4 comma-separated numbers.')
        try:
            values = [float(p) for p in parts]
        except ValueError as e:
            raise ValueError(f'bbox values must be numbers: {parts}') from e
    else:
        if len(bbox) != 4:
            raise ValueError(
                'bbox must contain exactly 4 numbers: [min_lon, min_lat, max_lon, max_lat].'
            )
        values = [float(v) for v in bbox]
    min_lon, min_lat, max_lon, max_lat = values
    return min_lon, min_lat, max_lon, max_lat
