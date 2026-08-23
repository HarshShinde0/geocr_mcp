"""Earth observation (EO) dataset discovery over STAC catalogs.

This module is the bridge between live EO archives and the GeoCroissant
format:

1. ``search_collections`` / ``search_scenes`` discover datasets and scenes
   from registered STAC APIs via pystac-client.
2. ``geocroissant_from_stac`` converts STAC results into a GeoCroissant
   JSON-LD document which is then validated by the official ``mlcroissant``
   library in the tool layer.

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
    cid = catalog_id or next(iter(catalogs.get_config()['catalogs']))
    return catalogs.get_catalog(cid)


def list_catalogs() -> list[dict[str, Any]]:
    """Lists all registered STAC catalogs with their modalities and topics."""
    entries = catalogs.list_catalogs()
    for entry in entries:
        entry['topics'] = sorted(catalogs.topics().keys())
    return entries


def resolve_topic(query: str) -> tuple[list[str], list[str]]:
    """Resolves a free-text query against the topics map.

    Returns (matched_topics, collections). Topics that are substrings of
    another matched topic (e.g. 'fire' inside 'wildfire') are dropped.
    Falls back to the multimodal default when nothing matches.
    """
    topics = catalogs.topics()
    query_lower = (query or '').lower()
    matched = [topic for topic in topics if topic in query_lower]
    # Drop redundant sub-topic matches ('fire' ⊂ 'wildfire').
    matched = [t for t in matched if not any(t != o and t in o for o in matched)]
    if not matched:
        return [], list(topics.get('multimodal', []))
    collections: list[str] = []
    for topic in matched:
        for coll in topics[topic]:
            if coll not in collections:
                collections.append(coll)
    return matched, collections


def guess_modality(collection: dict[str, Any]) -> str | None:
    """Guesses the sensor modality of a STAC collection from its metadata."""
    text = ' '.join(
        str(collection.get(key) or '') for key in ('id', 'title', 'description')
    ).lower()
    keywords = collection.get('keywords') or []
    if isinstance(keywords, list):
        text += ' ' + ' '.join(str(k).lower() for k in keywords)
    for modality, hints in catalogs.modality_hints():
        if any(hint in text for hint in hints):
            return modality
    return None


def _open_client(url: str):
    """Opens a STAC client (import kept local for cheap module load)."""
    import pystac_client

    return pystac_client.Client.open(url)


def search_collections(
    query: str = '',
    modality: str | None = None,
    limit: int = 15,
) -> dict[str, Any]:
    """Searches EO datasets across Earth Search by theme or free text.

    Resolution order:
    1. TOPICS map hit (e.g. "flood", "ndvi") -> curated collections.
    2. Otherwise: keyword match against live collection metadata
       (id/title/description), classified by modality heuristic.
    Collection summaries are fetched from the live API.
    """
    if modality and modality not in catalogs.modalities():
        raise ValueError(
            f'Unknown modality "{modality}". Choose one of {list(catalogs.modalities())}.'
        )
    cat = get_catalog()
    topics, themed_collections = resolve_topic(query)
    terms = [t.lower() for t in (query or '').split() if t.strip()]

    client = _open_client(cat['url'])
    results: list[dict[str, Any]] = []

    def _summarize(coll: dict[str, Any]) -> dict[str, Any]:
        extent = (coll.get('extent') or {}).get('temporal') or {}
        intervals = extent.get('interval') or [[]]
        interval = intervals[0] if intervals else []
        return {
            'catalog': cat['id'],
            'collection': coll.get('id'),
            'title': coll.get('title') or coll.get('id'),
            'description': (coll.get('description') or '')[:280],
            'modality': guess_modality(coll),
            'license': coll.get('license'),
            'temporal_extent': [
                i
                for i in (
                    interval[0] if len(interval) > 0 else None,
                    interval[1] if len(interval) > 1 else None,
                )
                if i
            ],
        }

    all_collections = [c.to_dict() for c in client.get_collections()]
    by_id = {c.get('id'): c for c in all_collections}

    if topics:
        # Themed resolution: exact collections from the topic map.
        for cid in themed_collections:
            coll = by_id.get(cid)
            if coll is not None:
                results.append(_summarize(coll))
    else:
        for coll in all_collections:
            guessed = guess_modality(coll)
            if modality and guessed != modality:
                continue
            text = ' '.join(
                str(coll.get(key) or '') for key in ('id', 'title', 'description')
            ).lower()
            if terms and not any(term in text for term in terms):
                continue
            results.append(_summarize(coll))
            if len(results) >= limit:
                break

    return {
        'query': query,
        'matched_topics': topics,
        'count': len(results),
        'collections': results,
    }


def default_collections_for(modality: str | None) -> list[str]:
    """Curated collection ids for a modality (all modalities when None)."""
    cat = get_catalog()
    if not modality:
        return [c for lists in cat['common'].values() for c in lists]
    return list(cat['common'].get(modality, []))


def _optical_collections() -> set[str]:
    """Collection ids whose items carry `eo:cloud_cover` (optical only).

    The STAC `query` extension drops every item lacking the filtered
    property, so applying a cloud filter to radar/elevation/aerial
    collections returns zero scenes (verified live against Earth Search:
    sentinel-1-grd goes from 2343 hits to 0 with `eo:cloud_cover < 20`).
    """
    return set(get_catalog()['common'].get('optical', []))


# Approximate extent of NAIP coverage (contiguous United States). Searches
# whose bbox lies fully outside this envelope would return zero scenes.
_CONUS_BBOX = (-125.0, 24.5, -66.0, 49.5)


def _bboxes_overlap(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    """Axis-aligned bbox intersection test in [min_lon, min_lat, max_lon, max_lat]."""
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


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
    modality: str | None,
    bbox4: tuple[float, float, float, float],
) -> tuple[list[str], list[str]]:
    """Resolves the target collection ids, applying coverage guards.

    Returns the targets plus human-readable notes about adjustments (NAIP is
    dropped when the bbox lies outside its CONUS-only footprint).
    """
    targets = (
        list(collections) if collections is not None else default_collections_for(modality)
    )
    if not targets:
        raise ValueError(
            'No known collections for this search. Pass explicit '
            '`collections` or use `search_eo_datasets` first.'
        )
    notes: list[str] = []
    if 'naip' in targets and not _bboxes_overlap(bbox4, _CONUS_BBOX):
        targets = [c for c in targets if c != 'naip']
        notes.append(
            'naip excluded: it covers the contiguous United States only and '
            'the requested bbox lies outside CONUS.'
        )
        if not targets:
            raise ValueError(
                'The only requested collection (naip) covers the contiguous '
                'United States; provide a bbox inside the US.'
            )
    return targets, notes


def _query_kwargs(
    targets: list[str],
    datetime_range: str | None,
    max_cloud_cover: float | None,
    page_limit: int,
    max_items: int | None,
    notes: list[str],
) -> dict[str, Any]:
    """Builds STAC /search parameters with property-aware filtering guards.

    - datetime filtering is skipped when every target collection is a static
      mosaic (e.g. elevation), which carries no meaningful acquisition time.
    - cloud-cover querying applies only when every target is optical, because
      the STAC `query` extension silently drops items lacking the property.
    """
    kwargs: dict[str, Any] = {
        'collections': targets,
        # Newest acquisitions first (Earth Search supports item-search#sort).
        'sortby': ['-properties.datetime'],
        # pystac-client: `limit` is the page size.
        'limit': page_limit,
    }
    if max_items is not None:
        kwargs['max_items'] = max_items
    all_static = all(c in catalogs.static_collections() for c in targets)
    if datetime_range:
        if all_static:
            notes.append(
                'datetime_range ignored: every target collection is a static '
                'mosaic without acquisition times.'
            )
        else:
            kwargs['datetime'] = datetime_range
    if max_cloud_cover is not None and all(c in _optical_collections() for c in targets):
        kwargs['query'] = {'eo:cloud_cover': {'lt': float(max_cloud_cover)}}
    return kwargs


def search_scenes(
    bbox: list[float],
    collections: list[str] | None = None,
    modality: str | None = None,
    datetime_range: str | None = None,
    max_cloud_cover: float | None = catalogs.default_cloud_cover(),
    limit: int = 10,
) -> dict[str, Any]:
    """Searches satellite scenes (STAC Items) inside a bounding box.

    Returns summarized scenes plus the raw STAC item dicts needed by
    ``geocroissant_from_stac``.
    """
    cat = get_catalog()
    bbox4 = _validated_bbox(bbox)
    target_collections, notes = _resolve_targets(collections, modality, bbox4)

    capped_limit = max(1, min(int(limit), 50))
    kwargs = _query_kwargs(
        targets=target_collections,
        datetime_range=datetime_range,
        max_cloud_cover=max_cloud_cover,
        page_limit=min(capped_limit, 25),
        max_items=capped_limit,
        notes=notes,
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
    modality: str | None = None,
    datetime_range: str | None = None,
    max_cloud_cover: float | None = None,
) -> dict[str, Any]:
    """Counts matching scenes per collection without transferring items.

    Issues a `limit=1` STAC item search per collection and reads its
    ``numberMatched`` context total - a cheap availability check before
    running a full :func:`search_scenes`. The same property-aware guards
    apply: cloud filtering only for all-optical targets, datetime skipped
    for static mosaics, NAIP dropped outside CONUS.
    """
    cat = get_catalog()
    bbox4 = _validated_bbox(bbox)
    targets, notes = _resolve_targets(collections, modality, bbox4)
    base = _query_kwargs(
        targets=targets,
        datetime_range=datetime_range,
        max_cloud_cover=max_cloud_cover,
        page_limit=1,
        max_items=None,
        notes=notes,
    )
    del base['sortby']  # irrelevant when no items are transferred

    client = _open_client(cat['url'])
    counts: dict[str, int | None] = {}
    for cid in targets:
        try:
            matched = int(client.search(**{**base, 'collections': [cid]}).matched())
            counts[cid] = matched
        except Exception:
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

    Beyond the common fields, modality-specific properties are surfaced:
    SAR (`sar:polarizations`, `sar:instrument_mode`, `sat:orbit_state`),
    Sentinel-2 scene classification (`s2:water_percentage`, ...), Landsat
    WRS tiling, NAIP state/year and storage flags.
    """
    props = item.get('properties') or {}
    summary = {
        'scene_id': item.get('id'),
        'collection': item.get('collection'),
        'datetime': props.get('datetime') or props.get('start_datetime'),
        'platform': props.get('platform'),
        'cloud_cover': props.get('eo:cloud_cover'),
        'epsg': _item_epsg(item),
        'gsd': props.get('gsd'),
        'bbox': item.get('bbox'),
        'asset_keys': sorted((item.get('assets') or {}).keys()),
    }
    # Modality-specific extras (only present when the collection provides them).
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
    """Collects ordered, de-duplicated eo:bands across items.

    Band labels differ per Earth Search collection (`name` on Sentinel-2,
    `common_name` on Landsat); unlabeled bands fall back to the asset key so
    every raster band surfaces.
    """
    bands_by_name: dict[str, dict[str, Any]] = {}
    for item in raw_items:
        for asset_key, asset in (item.get('assets') or {}).items():
            for band in asset.get('eo:bands') or []:
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
    """Native EPSG from either `proj:epsg` (int) or `proj:code` string."""
    props = item.get('properties') or {}
    epsg = props.get('proj:epsg')
    if isinstance(epsg, int):
        return epsg
    code = props.get('proj:code')
    if isinstance(code, str) and code.upper().startswith('EPSG:'):
        try:
            return int(code.split(':', 1)[1])
        except ValueError:
            return None
    return None


def _s3_to_https(href: str, region: str | None) -> str | None:
    """Translates `s3://bucket/key` hrefs to public https form.

    Earth Search assets come in two shapes: sentinel-2-c1-l2a ships https
    COG hrefs, while Sentinel-1, Landsat, Copernicus DEM and NAIP only
    expose `s3://` hrefs. Without translation, `_pick_asset_urls` would
    produce zero distributions for those collections.
    """
    if not href.startswith('s3://'):
        return href
    rest = href[len('s3://') :]
    bucket, _, key = rest.partition('/')
    if not key:
        return None
    host = f'{bucket}.s3.{region}.amazonaws.com' if region else f'{bucket}.s3.amazonaws.com'
    return f'https://{host}/{key}'


def _pick_asset_urls(item: dict[str, Any], max_assets: int) -> list[tuple[str, str, str | None]]:
    """Picks asset URLs as (asset_key, https_href, encoding_format).

    `s3://` hrefs are translated to their https equivalent using the
    item's storage scheme region; metadata assets are skipped in favor
    of actual data bands.
    """
    storage = _storage_info(item)
    picks: list[tuple[str, str, str | None]] = []
    assets = sorted((item.get('assets') or {}).items())
    # Data bands first, then anything else (metadata/thumbnail last resort).
    ranked = sorted(
        assets,
        key=lambda kv: 0 if 'data' in (kv[1].get('roles') or []) else 1,
    )
    for key, asset in ranked:
        href = _s3_to_https(asset.get('href') or '', storage.get('region'))
        if not href or not href.startswith(('http://', 'https://')):
            continue
        if 'metadata' in (asset.get('roles') or []):
            continue
        fmt = asset.get('type') or asset.get('media_type')
        picks.append((key, href, fmt))
        if len(picks) >= max_assets:
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
    max_distribution_assets: int = 6,
    cite_as: str = '',
) -> dict[str, Any]:
    """Builds a GeoCroissant JSON-LD document from Earth Search results.

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
        dt = (item.get('properties') or {}).get('datetime')
        if dt:
            datetimes.append(str(dt))
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
    if epsgs:
        doc['geocr:recordEndpoint'] = get_catalog()['url']
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

    # --- Distribution (FileObjects for direct asset access) -----------
    distribution: list[dict[str, Any]] = []
    selected_items = raw_items[: max(1, max_distribution_assets // 2)]
    for item in selected_items:
        for key, href, fmt in _pick_asset_urls(item, max_assets=2):
            if len(distribution) >= max_distribution_assets:
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
    if band_names:
        fields[-1]['geocr:bandConfiguration'] = {
            '@type': 'geocr:BandConfiguration',
            'geocr:totalBands': len(band_names),
            'geocr:bandNamesList': band_names,
        }

    data_rows = []
    for item in raw_items:
        props = item.get('properties') or {}
        cloud = props.get('eo:cloud_cover')
        epsg = _item_epsg(item)
        first_url = _pick_asset_urls(item, max_assets=1)
        data_rows.append(
            {
                f'{rs}/scene_id': str(item.get('id') or ''),
                f'{rs}/collection': str(item.get('collection') or ''),
                f'{rs}/datetime': str(props.get('datetime') or ''),
                f'{rs}/cloud_cover': float(cloud) if cloud is not None else '',
                f'{rs}/epsg': int(epsg) if isinstance(epsg, int) else '',
                f'{rs}/image_url': first_url[0][1] if first_url else '',
            }
        )

    doc['recordSet'] = [
        {
            '@type': 'cr:RecordSet',
            '@id': rs,
            'name': rs.replace('_', ' ').title(),
            'description': 'Satellite scenes returned by the Earth Search STAC query.',
            'key': {'@id': f'{rs}/scene_id'},
            'field': fields,
            'data': data_rows,
        }
    ]
    return doc
