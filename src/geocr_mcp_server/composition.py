"""Composition of independent STAC searches into one GeoCroissant dataset."""

import re
from geocr_mcp_server import eo
from typing import Any


def _required_text(source: dict[str, Any], field: str, index: int) -> str:
    value = source.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'sources[{index}].{field} must be a non-empty string.')
    return value.strip()


def _record_set_id(source_id: str) -> str:
    normalized = re.sub(r'[^A-Za-z0-9_]+', '_', source_id).strip('_').lower()
    if not normalized:
        raise ValueError('source_id must contain at least one letter or number.')
    return f'scenes_{normalized}'


def _normalize_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not sources:
        raise ValueError('Pass at least one source search.')

    normalized = []
    source_ids: set[str] = set()
    record_set_ids: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise ValueError(f'sources[{index}] must be an object.')
        catalog_id = _required_text(source, 'catalog_id', index)
        collection_id = _required_text(source, 'collection_id', index)
        source_id = source.get('source_id') or f'source-{index + 1}'
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError(f'sources[{index}].source_id must be a non-empty string.')
        source_id = source_id.strip()
        record_set_id = _record_set_id(source_id)
        if source_id in source_ids or record_set_id in record_set_ids:
            raise ValueError(f'Each source_id must be unique; duplicate `{source_id}`.')
        source_ids.add(source_id)
        record_set_ids.add(record_set_id)

        bbox = source.get('bbox')
        if not isinstance(bbox, list):
            raise ValueError(f'sources[{index}].bbox must be a four-number list.')
        limit = int(source.get('limit', 5))
        if not 1 <= limit <= 50:
            raise ValueError(f'sources[{index}].limit must be between 1 and 50.')
        normalized.append(
            {
                'source_id': source_id,
                'record_set_id': record_set_id,
                'catalog_id': catalog_id,
                'collection_id': collection_id,
                'bbox': bbox,
                'datetime_range': source.get('datetime_range'),
                'max_cloud_cover': source.get('max_cloud_cover'),
                'limit': limit,
            }
        )
    return normalized


def search_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Runs each explicit catalog and collection search independently."""
    results = []
    for source in _normalize_sources(sources):
        search = eo.search_scenes(
            bbox=source['bbox'],
            collections=[source['collection_id']],
            datetime_range=source['datetime_range'],
            max_cloud_cover=source['max_cloud_cover'],
            limit=source['limit'],
            catalog_id=source['catalog_id'],
        )
        results.append({**source, 'search': search})
    return results


def compose_document(
    *,
    name: str,
    description: str,
    license_url: str,
    creators: list[str] | None,
    source_results: list[dict[str, Any]],
    spatial_bias: str = '',
    sampling_strategy: str = '',
    data_collection: str = '',
    data_biases: list[str] | None = None,
    data_limitations: list[str] | None = None,
    data_use_cases: list[str] | None = None,
    data_social_impact: str = '',
    personal_sensitive_information: list[str] | None = None,
    has_synthetic_data: bool | None = None,
    rai_properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Builds one dataset while retaining a RecordSet for every source search."""
    raw_items = [
        item
        for result in source_results
        for item in result['search'].get('_raw_items', [])
    ]
    document = eo.geocroissant_from_stac(
        name=name,
        description=description,
        license_url=license_url,
        creators=creators,
        raw_items=raw_items,
        catalog_id=source_results[0]['catalog_id'],
        spatial_bias=spatial_bias,
        sampling_strategy=sampling_strategy,
        data_collection=data_collection,
        data_biases=data_biases,
        data_limitations=data_limitations,
        data_use_cases=data_use_cases,
        data_social_impact=data_social_impact,
        personal_sensitive_information=personal_sensitive_information,
        has_synthetic_data=has_synthetic_data,
        rai_properties=rai_properties,
    )
    document.pop('geocr:recordEndpoint', None)
    document.pop('geocr:bandConfiguration', None)
    document.pop('geocr:spectralBandMetadata', None)
    document.pop('additionalProperty', None)

    distributions = []
    record_sets = []
    for result in source_results:
        source_id = result['source_id']
        record_set_id = result.get('record_set_id') or _record_set_id(source_id)
        source_document = eo.geocroissant_from_stac(
            name=name,
            description=description,
            license_url=license_url,
            creators=creators,
            raw_items=result['search']['_raw_items'],
            record_set_name=record_set_id,
            catalog_id=result['catalog_id'],
        )
        for entry in source_document.get('distribution', []):
            copied = dict(entry)
            copied['@id'] = f'{record_set_id}__{entry["@id"]}'
            distributions.append(copied)

        record_set = source_document['recordSet'][0]
        record_set['description'] = (
            f'STAC records from catalog `{result["catalog_id"]}` and collection '
            f'`{result["collection_id"]}`.'
        )
        source_field = {
            '@type': 'cr:Field',
            '@id': f'{record_set_id}/source_id',
            'name': 'source_id',
            'dataType': 'sc:Text',
        }
        catalog_field = {
            '@type': 'cr:Field',
            '@id': f'{record_set_id}/catalog_id',
            'name': 'catalog_id',
            'dataType': 'sc:Text',
        }
        record_set['field'].extend([source_field, catalog_field])
        for row in record_set['data']:
            row[source_field['@id']] = source_id
            row[catalog_field['@id']] = result['catalog_id']
        record_sets.append(record_set)

    document['distribution'] = distributions
    document['recordSet'] = record_sets
    return document


def asset_manifest(source_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Returns provider-supplied identity and raster metadata for every asset."""
    manifest = []
    for result in source_results:
        for item in result['search'].get('_raw_items', []):
            item_epsg = eo._item_epsg(item)
            polarizations = (item.get('properties') or {}).get('sar:polarizations')
            for asset_key, asset in (item.get('assets') or {}).items():
                href = asset.get('href')
                if not isinstance(href, str) or not href:
                    continue
                entry = {
                    'source_id': result['source_id'],
                    'catalog_id': result['catalog_id'],
                    'collection_id': result['collection_id'],
                    'scene_id': str(item.get('id') or ''),
                    'asset_key': asset_key,
                    'href': href,
                }
                optional = {
                    'media_type': asset.get('type') or asset.get('media_type'),
                    'roles': asset.get('roles'),
                    'epsg': asset.get('proj:epsg') or item_epsg,
                    'shape': asset.get('proj:shape'),
                    'transform': asset.get('proj:transform'),
                    'bands': asset.get('eo:bands') or asset.get('raster:bands'),
                    'polarizations': polarizations,
                }
                entry.update({key: value for key, value in optional.items() if value is not None})
                manifest.append(entry)
    return manifest
