"""Earth observation (EO) dataset discovery over STAC catalogs.

This module is the bridge between live EO archives and the GeoCroissant
format:

1. ``search_collections`` / ``search_scenes`` discover datasets and scenes
   from registered STAC APIs via pystac-client.
2. ``geocroissant_from_stac`` converts STAC results into a GeoCroissant
    JSON-LD document. The tool layer then runs metadata validation with the
    configured ``mlcroissant`` package.

The catalog registry itself is data-driven: see
``geocr_mcp_server/catalogs.py`` and the shipped
``config/catalogs.yaml``. Collection ids for Earth Search were audited
against the live API.

All functions here are synchronous and network-facing; the MCP tools wrap
them with ``asyncio.to_thread``.
"""

from geocr_mcp_server import catalogs
from geocr_mcp_server.spec import (
    CROISSANT_CONFORMANCE,
    GEO_CONFORMANCE,
    official_context,
)
from typing import Any


def get_catalog(catalog_id: str | None = None) -> dict[str, Any]:
    """Returns catalog metadata by id from the YAML registry."""
    return catalogs.get_catalog(catalog_id)


def list_catalogs() -> list[dict[str, Any]]:
    """Lists all registered STAC catalogs."""
    return catalogs.list_catalogs()


def _open_client(url: str):
    """Opens a STAC client (import kept local for cheap module load)."""
    import pystac_client

    return pystac_client.Client.open(url)


def search_collections(
    limit: int = 15,
    offset: int = 0,
    catalog_id: str | None = None,
) -> dict[str, Any]:
    """Lists a page of live EO datasets from a registered STAC catalog."""
    cat = get_catalog(catalog_id)
    capped_limit = max(1, min(int(limit), 500))
    page_offset = max(0, int(offset))

    client = _open_client(cat['url'])

    def _summarize(coll: dict[str, Any]) -> dict[str, Any]:
        extent = coll.get('extent') or {}
        temporal = extent.get('temporal') or {}
        intervals = temporal.get('interval') or [[]]
        interval = intervals[0] if intervals else []
        spatial = extent.get('spatial') or {}
        providers = coll.get('providers') or []
        return {
            'catalog': cat['id'],
            'collection': coll.get('id'),
            'title': coll.get('title') or coll.get('id'),
            'description': (coll.get('description') or '')[:1000],
            'license': coll.get('license'),
            'keywords': coll.get('keywords') or [],
            'providers': [
                {
                    'name': provider.get('name'),
                    'roles': provider.get('roles') or [],
                    'url': provider.get('url'),
                }
                for provider in providers
            ],
            'spatial_extent': spatial.get('bbox') or [],
            'temporal_extent': [
                i
                for i in (
                    interval[0] if len(interval) > 0 else None,
                    interval[1] if len(interval) > 1 else None,
                )
                if i
            ],
            'item_asset_keys': sorted((coll.get('item_assets') or {}).keys()),
            'summaries': coll.get('summaries') or {},
        }

    all_collections = [c.to_dict() for c in client.get_collections()]
    page = all_collections[page_offset : page_offset + capped_limit]
    results = [_summarize(coll) for coll in page]
    next_offset = page_offset + len(results)

    return {
        'catalog': cat['id'],
        'offset': page_offset,
        'count': len(results),
        'total_catalog_collections': len(all_collections),
        'truncated': next_offset < len(all_collections),
        'next_offset': next_offset if next_offset < len(all_collections) else None,
        'collections': results,
    }


def get_collection_details(
    collection_id: str,
    catalog_id: str | None = None,
) -> dict[str, Any]:
    """Returns provider STAC metadata for one collection."""
    requested_id = collection_id.strip()
    if not requested_id:
        raise ValueError('collection_id must not be empty.')
    cat = get_catalog(catalog_id)
    collection = _open_client(cat['url']).get_collection(requested_id)
    return {
        'catalog': cat['id'],
        'collection': collection.to_dict(),
    }


def _validated_bbox(bbox: list[float]) -> tuple[float, float, float, float]:
    """Validates a [min_lon, min_lat, max_lon, max_lat] bbox."""
    if len(bbox) != 4:
        raise ValueError('bbox must be [min_lon, min_lat, max_lon, max_lat].')
    min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox)
    if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
        raise ValueError('Longitudes must be within [-180, 180].')
    if min_lat > max_lat:
        raise ValueError('bbox min_lat must be <= max_lat.')
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        raise ValueError('Latitudes must be within [-90, 90].')
    return min_lon, min_lat, max_lon, max_lat


def _resolve_targets(
    collections: list[str] | None,
) -> list[str]:
    """Validates the explicit target collection ids."""
    targets = list(collections or [])
    if not targets:
        raise ValueError(
            'Pass at least one explicit `collections` id. Use '
            '`search_eo_datasets` to list the selected catalog first.'
        )
    return targets


def _query_kwargs(
    targets: list[str],
    bbox: tuple[float, float, float, float],
    datetime_range: str | None,
    max_cloud_cover: float | None,
    page_limit: int,
    max_items: int | None,
) -> dict[str, Any]:
    """Builds STAC search parameters from explicit user filters."""
    kwargs: dict[str, Any] = {
        'collections': targets,
        'bbox': list(bbox),
        # Newest acquisitions first (Earth Search supports item-search#sort).
        'sortby': ['-properties.datetime'],
        # pystac-client: `limit` is the page size.
        'limit': page_limit,
    }
    if max_items is not None:
        kwargs['max_items'] = max_items
    if datetime_range:
        kwargs['datetime'] = datetime_range
    if max_cloud_cover is not None:
        kwargs['query'] = {'eo:cloud_cover': {'lt': float(max_cloud_cover)}}
    return kwargs


def search_scenes(
    bbox: list[float],
    collections: list[str] | None = None,
    datetime_range: str | None = None,
    max_cloud_cover: float | None = None,
    limit: int = 10,
    catalog_id: str | None = None,
) -> dict[str, Any]:
    """Searches satellite scenes (STAC Items) inside a bounding box.

    Returns summarized scenes plus the raw STAC item dicts needed by
    ``geocroissant_from_stac``.
    """
    cat = get_catalog(catalog_id)
    bbox4 = _validated_bbox(bbox)
    target_collections = _resolve_targets(collections)
    notes: list[str] = []

    capped_limit = max(1, min(int(limit), 50))
    kwargs = _query_kwargs(
        targets=target_collections,
        bbox=bbox4,
        datetime_range=datetime_range,
        max_cloud_cover=max_cloud_cover,
        page_limit=min(capped_limit, 25),
        max_items=capped_limit,
    )

    client = _open_client(cat['url'])
    search = client.search(**kwargs)
    raw_items = [item.to_dict() for item in search.items()]

    scenes = [_summarize_item(item) for item in raw_items]
    return {
        'catalog': cat['id'],
        'catalog_name': cat['name'],
        'collections_searched': target_collections,
        'bbox': list(bbox4),
        'datetime_range': datetime_range if 'datetime' in kwargs else None,
        'max_cloud_cover': max_cloud_cover if 'query' in kwargs else None,
        'cloud_filter_applied': 'query' in kwargs,
        'notes': notes,
        'scene_count': len(scenes),
        'scenes': scenes,
        '_raw_items': raw_items,
    }


def count_scenes(
    bbox: list[float],
    collections: list[str] | None = None,
    datetime_range: str | None = None,
    max_cloud_cover: float | None = None,
    catalog_id: str | None = None,
) -> dict[str, Any]:
    """Counts matching scenes per collection without transferring items."""
    cat = get_catalog(catalog_id)
    bbox4 = _validated_bbox(bbox)
    targets = _resolve_targets(collections)
    notes: list[str] = []
    base = _query_kwargs(
        targets=targets,
        bbox=bbox4,
        datetime_range=datetime_range,
        max_cloud_cover=max_cloud_cover,
        page_limit=1,
        max_items=None,
    )
    del base['sortby']  # irrelevant when no items are transferred

    client = _open_client(cat['url'])
    counts: dict[str, int | None] = {}
    for cid in targets:
        try:
            matched = int(client.search(**{**base, 'collections': [cid]}).matched())
            counts[cid] = matched
        except Exception:  # pragma: no cover - requires an upstream protocol failure
            counts[cid] = None
            notes.append(f'count unavailable for `{cid}` (no numberMatched reported).')
    available = [v for v in counts.values() if v is not None]
    return {
        'catalog': cat['id'],
        'bbox': list(bbox4),
        'datetime_range': datetime_range if 'datetime' in base else None,
        'cloud_filter_applied': 'query' in base,
        'counts': counts,
        'total_matched': sum(available),
        'notes': notes,
    }


def _summarize_item(item: dict[str, Any]) -> dict[str, Any]:
    """Compact scene summary safe to return to an LLM.

    Beyond the common fields, STAC extension properties are surfaced:
    SAR (`sar:polarizations`, `sar:instrument_mode`, `sat:orbit_state`),
    Sentinel-2 scene classification (`s2:water_percentage`, ...), Landsat
    WRS tiling, NAIP state/year and storage flags.
    """
    props = item.get('properties') or {}
    summary = {
        'scene_id': item.get('id'),
        'collection': item.get('collection'),
        'datetime': props.get('datetime') or props.get('start_datetime'),
        'end_datetime': props.get('end_datetime'),
        'platform': props.get('platform'),
        'cloud_cover': props.get('eo:cloud_cover'),
        'epsg': _item_epsg(item),
        'gsd': props.get('gsd'),
        'bbox': item.get('bbox'),
        'asset_keys': sorted((item.get('assets') or {}).keys()),
    }
    # STAC extension properties (only present when the item provides them).
    extras = {
        'sar:polarizations': props.get('sar:polarizations'),
        'sar:instrument_mode': props.get('sar:instrument_mode'),
        'sat:orbit_state': props.get('sat:orbit_state'),
        'view:sun_elevation': props.get('view:sun_elevation'),
        's2:water_percentage': props.get('s2:water_percentage'),
        'landsat:wrs_path_row': (
            f'{props.get("landsat:wrs_path")}/{props.get("landsat:wrs_row")}'
            if props.get('landsat:wrs_path')
            else None
        ),
        'naip:state': props.get('naip:state'),
        'storage:region': props.get('storage:region'),
    }
    summary.update({k: v for k, v in extras.items() if v is not None})
    return {k: v for k, v in summary.items() if v is not None}


def _collect_bands(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collects ordered, de-duplicated EO or raster bands across items.

    Band labels differ per Earth Search collection (`name` on Sentinel-2,
    `common_name` on Landsat); unlabeled bands fall back to the asset key so
    every raster band surfaces.
    """
    bands_by_name: dict[str, dict[str, Any]] = {}
    for item in raw_items:
        for asset_key, asset in (item.get('assets') or {}).items():
            for band in asset.get('eo:bands') or asset.get('raster:bands') or []:
                name = band.get('name') or band.get('common_name') or asset_key
                existing = bands_by_name.get(name)
                if existing is None or (
                    band.get('center_wavelength') is not None
                    and existing.get('center_wavelength') is None
                ):
                    enriched = dict(band)
                    enriched.setdefault('name', name)
                    bands_by_name[name] = enriched
    return sorted(
        bands_by_name.values(),
        key=lambda b: (
            b.get('center_wavelength') is None,
            b.get('center_wavelength') or 0,
        ),
    )


def _spectral_entries(bands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Converts eo:bands into spec-compliant geocr:spectralBandMetadata.

    STAC stores wavelengths/bandwidths in micrometers; GeoCroissant examples
    use nanometers, so values are converted and wrapped in QuantitativeValue
    nodes exactly as in docs/croissant-geo-spec.md.
    """

    def _qvalue(value: float | None) -> dict[str, Any] | None:
        if value is None:
            return None
        return {
            '@type': 'QuantitativeValue',
            'value': round(float(value) * 1000.0, 1),
            'unitText': 'nm',
        }

    entries = []
    for band in bands:
        name = band.get('name')
        if not name:
            continue
        entry: dict[str, Any] = {'@type': 'geocr:SpectralBand', 'name': str(name)}
        center = _qvalue(band.get('center_wavelength'))
        if center:
            entry['geocr:centerWavelength'] = center
        width = _qvalue(band.get('bandwidth') or band.get('full_width_half_max'))
        if width:
            entry['geocr:bandwidth'] = width
        entries.append(entry)
    return entries


def _storage_info(item: dict[str, Any]) -> dict[str, Any]:
    """Extracts bucket/region/requester_pays from an item's storage metadata.

    Earth Search `/search` items use the storage extension v2 shape
    (``storage:schemes`` on properties, ``storage:refs`` on assets);
    ``/collections/{id}/items`` items use flat ``storage:region`` /
    ``storage:requester_pays`` properties. Both are handled.
    """
    schemes = (item.get('properties') or {}).get('storage:schemes') or {}
    if isinstance(schemes, dict) and schemes:
        first = next(iter(schemes.values()))
        if isinstance(first, dict):
            return {
                'bucket': first.get('bucket'),
                'region': first.get('region'),
                'requester_pays': bool(first.get('requester_pays')),
            }
    props = item.get('properties') or {}
    return {
        'bucket': None,
        'region': props.get('storage:region'),
        'requester_pays': bool(props.get('storage:requester_pays')),
    }


def _item_epsg(item: dict[str, Any]) -> int | None:
    """Native EPSG from item properties or asset-level projection fields."""
    candidates = [item.get('properties') or {}]
    candidates.extend((item.get('assets') or {}).values())
    for candidate in candidates:
        epsg = candidate.get('proj:epsg')
        if isinstance(epsg, int):
            return epsg
        code = candidate.get('proj:code')
        if isinstance(code, str) and code.upper().startswith('EPSG:'):
            try:
                return int(code.split(':', 1)[1])
            except ValueError:
                continue
    return None


def _pick_asset_urls(
    item: dict[str, Any], max_assets: int | None = None
) -> list[tuple[str, str, str | None]]:
    """Picks asset URLs as (asset_key, original_href, encoding_format).

    Provider hrefs are preserved because their scheme can carry access
    semantics; metadata assets are skipped in favor of data assets.
    """
    picks: list[tuple[str, str, str | None]] = []
    assets = sorted((item.get('assets') or {}).items())
    # Data bands first, then anything else (metadata/thumbnail last resort).
    ranked = sorted(
        assets,
        key=lambda kv: (
            0
            if kv[0] == 'cog_default'
            else 1
            if 'data' in (kv[1].get('roles') or [])
            else 2
        ),
    )
    for key, asset in ranked:
        href = asset.get('href')
        if not isinstance(href, str) or not href:
            continue
        if 'metadata' in (asset.get('roles') or []):
            continue
        fmt = asset.get('type') or asset.get('media_type')
        picks.append((key, href, fmt))
        if max_assets is not None and len(picks) >= max_assets:
            break
    return picks


def geocroissant_from_stac(
    *,
    name: str,
    description: str,
    license_url: str,
    creators: list[str] | None,
    raw_items: list[dict[str, Any]],
    record_set_name: str = 'scenes',
    max_distribution_assets: int | None = None,
    cite_as: str = '',
    catalog_id: str | None = None,
) -> dict[str, Any]:
    """Builds a GeoCroissant JSON-LD document from STAC results.

    The generated document includes schema.org coverage (bbox + temporal),
    GeoCroissant properties (CRS, record endpoint, band configuration and
    spectral band metadata derived from `eo:bands`), one FileObject per picked
    asset URL, and a RecordSet with inline rows - one per scene - so records
    can be materialized without downloads.
    """
    if not raw_items:
        raise ValueError('No STAC scenes found for this search; cannot generate GeoCroissant.')
    doc: dict[str, Any] = {
        '@context': official_context(),
        '@type': 'Dataset',
        'name': name,
        'conformsTo': [CROISSANT_CONFORMANCE, GEO_CONFORMANCE],
        # EO archives are live services; checksums are unknown at generation time.
        'isLiveDataset': True,
    }
    if description:
        doc['description'] = description
    if license_url:
        doc['license'] = license_url
    if cite_as:
        doc['citeAs'] = cite_as
    if creators:
        doc['creator'] = [{'@type': 'Organization', 'name': c} for c in creators]

    # --- Coverage -----------------------------------------------------
    lats: list[float] = []
    lons: list[float] = []
    datetimes: list[str] = []
    epsgs: set[int] = set()
    for item in raw_items:
        bbox = item.get('bbox') or []
        if len(bbox) == 4:
            lons.extend([float(bbox[0]), float(bbox[2])])
            lats.extend([float(bbox[1]), float(bbox[3])])
        props = item.get('properties') or {}
        datetimes.extend(
            str(value)
            for value in (
                props.get('datetime'),
                props.get('start_datetime'),
                props.get('end_datetime'),
            )
            if value
        )
        epsg = _item_epsg(item)
        if isinstance(epsg, int):
            epsgs.add(epsg)
    if lats and lons:
        doc['spatialCoverage'] = {
            '@type': 'Place',
            'geo': {
                '@type': 'GeoShape',
                'box': f'{min(lats)} {min(lons)} {max(lats)} {max(lons)}',
            },
        }
    if datetimes:
        doc['temporalCoverage'] = f'{min(datetimes)[:10]}/{max(datetimes)[:10]}'

    # --- Bands & spectral metadata ------------------------------------
    bands = _collect_bands(raw_items)
    band_names = [str(b['name']) for b in bands if b.get('name')]
    if band_names:
        doc['geocr:bandConfiguration'] = {
            '@type': 'geocr:BandConfiguration',
            'geocr:totalBands': len(band_names),
            'geocr:bandNamesList': band_names,
        }
        spectral = _spectral_entries(bands)
        if any('geocr:centerWavelength' in e for e in spectral):
            doc['geocr:spectralBandMetadata'] = spectral

    # Search results are EPSG:4326; native tile CRS recorded separately.
    doc['geocr:coordinateReferenceSystem'] = 'EPSG:4326'
    extra_properties: list[dict[str, Any]] = []
    doc['geocr:recordEndpoint'] = get_catalog(catalog_id)['url']
    if epsgs:
        extra_properties.append(
            {
                '@type': 'PropertyValue',
                'name': 'nativeTileCRS(EPSG)',
                'value': sorted(epsgs),
            }
        )

    # Reflectance conversion factors (raster:bands scale/offset): physical
    # value = DN * scale + offset. Critical for ML preprocessing.
    scales: dict[str, dict[str, float]] = {}
    for item in raw_items:
        for asset_key, asset in (item.get('assets') or {}).items():
            for band in asset.get('raster:bands') or []:
                scale = band.get('scale')
                if scale is None:
                    continue
                scales[asset_key] = {
                    'scale': float(scale),
                    'offset': float(band.get('offset') or 0.0),
                }
                break
        if len(scales) >= 6:
            break
    if scales:
        extra_properties.append(
            {
                '@type': 'PropertyValue',
                'name': 'reflectanceConversion(DN*scale+offset)',
                'value': scales,
            }
        )

    # Downstream access cost flags from STAC storage metadata.
    requester_pays = {
        str(item.get('collection') or '')
        for item in raw_items
        if _storage_info(item).get('requester_pays')
    }
    if requester_pays:
        extra_properties.append(
            {
                '@type': 'PropertyValue',
                'name': 'storageRequesterPays(collections)',
                'value': sorted(p for p in requester_pays if p),
            }
        )
    if extra_properties:
        doc['additionalProperty'] = extra_properties

    # --- Distribution (FileObjects preserving provider asset URIs) ----
    distribution: list[dict[str, Any]] = []
    for item in raw_items:
        for key, href, fmt in _pick_asset_urls(item):
            if (
                max_distribution_assets is not None
                and len(distribution) >= max_distribution_assets
            ):
                break
            entry = {
                '@type': 'cr:FileObject',
                '@id': f'{item.get("id")}_{key}',
                'name': f'{item.get("id")}_{key}',
                'encodingFormat': fmt or 'application/octet-stream',
                'contentUrl': href,
            }
            file_size = ((item.get('assets') or {}).get(key) or {}).get('file:size')
            if isinstance(file_size, int):
                entry['contentSize'] = str(file_size)
            distribution.append(entry)
        if max_distribution_assets is not None and len(distribution) >= max_distribution_assets:
            break
    if distribution:
        doc['distribution'] = distribution

    # --- RecordSet: one inline row per scene --------------------------
    rs = record_set_name
    field_specs = [
        ('scene_id', 'sc:Text'),
        ('collection', 'sc:Text'),
        ('datetime', 'sc:DateTime'),
        ('cloud_cover', 'sc:Float'),
        ('epsg', 'sc:Integer'),
        ('image_url', 'sc:URL'),
        ('asset_urls', 'sc:URL'),
    ]
    fields = []
    for fname, dtype in field_specs:
        fields.append(
            {
                '@type': 'cr:Field',
                '@id': f'{rs}/{fname}',
                'name': fname,
                'dataType': dtype,
            }
        )
    fields[-1]['isArray'] = True
    if band_names:
        image_field = next(field for field in fields if field['@id'] == f'{rs}/image_url')
        image_field['geocr:bandConfiguration'] = {
            '@type': 'geocr:BandConfiguration',
            'geocr:totalBands': len(band_names),
            'geocr:bandNamesList': band_names,
        }

    data_rows = []
    for item in raw_items:
        props = item.get('properties') or {}
        cloud = props.get('eo:cloud_cover')
        epsg = _item_epsg(item)
        asset_urls = _pick_asset_urls(item)
        data_rows.append(
            {
                f'{rs}/scene_id': str(item.get('id') or ''),
                f'{rs}/collection': str(item.get('collection') or ''),
                f'{rs}/datetime': str(
                    props.get('datetime') or props.get('start_datetime') or ''
                ),
                f'{rs}/cloud_cover': float(cloud) if cloud is not None else '',
                f'{rs}/epsg': int(epsg) if isinstance(epsg, int) else '',
                f'{rs}/image_url': asset_urls[0][1] if asset_urls else '',
                f'{rs}/asset_urls': [url for _, url, _ in asset_urls],
            }
        )

    doc['recordSet'] = [
        {
            '@type': 'cr:RecordSet',
            '@id': rs,
            'name': rs.replace('_', ' ').title(),
            'description': 'Earth observation records returned by the selected STAC query.',
            'key': {'@id': f'{rs}/scene_id'},
            'field': fields,
            'data': data_rows,
        }
    ]
    return doc
