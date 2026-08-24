# Earth Search STAC API Audit

Audited live on 2026-08-23 against `https://earth-search.aws.element84.com/v1`
(STAC 1.0.0, OGC API - Features). The details below record responses observed
on that date. Collection inventories, item counts, and service behavior may
change.

## 1. API surface

| Endpoint | Notes |
|---|---|
| `GET /` | Landing page with links to the service resources |
| `GET /conformance` | Implements: core, collections, ogcapi-features (+`#fields`, `#sort`, `#query`), item-search (+`#fields`, `#sort`, `#query`), aggregation v0.3 |
| `GET /api`, `GET /api.html` | OpenAPI 3.0 spec (served as **YAML** despite JSON accept) |
| `GET /collections` | Nine collections at the time of the audit |
| `GET /collections/{id}` | Collection extent, license, providers, `item_assets`, and `summaries` |
| `GET /collections/{id}/items` | Items in one collection; supports `bbox`, `datetime`, `limit`, pagination via `next` link |
| `GET /collections/{id}/items/{itemId}` | Single item |
| `POST/PUT/DELETE` on items | Advertised in OpenAPI but **read-only** in practice |
| `GET /search` | Simple filters: `bbox`, `intersects`, `datetime`, `collections`, `ids`, `limit`, `fields`, `sortby` |
| `POST /search` | GET filters plus `query` property filters |
| `GET /aggregations` | Lists `total_count`, `datetime_min/max`, `datetime_frequency` |
| `GET /aggregate` | Returned empty `aggregations` for the audited queries |

Key behaviors:

- A `query` filter excludes items that do not contain the requested property. For example,
  `{"eo:cloud_cover": {"lt": 20}}` returns `numberMatched: 0` on
  `sentinel-1-grd` (2343 unfiltered hits in the test bbox), `cop-dem-glo-30`
  and `naip`. Only apply cloud filters to optical collections.
- `sortby` works (verified): `[{"field": "properties.datetime",
  "direction": "desc"}]` returns newest first.
- `fields` works (verified): include/exclude trims responses.
- `/search` accepts date-only ranges (`2023-07-01/2023-09-30`).
  `/aggregate` required full RFC3339 timestamps during the audit.
- Pagination: cursor `next` links; page size capped (100 max per request);
  responses carry `numberMatched`/`numberReturned` (with `limit=1` this is a
  low-cost scene-count query).

## 2. Collections observed during the audit

| Collection | ~Items | Temporal | GSD (m) | Native EPSG | Storage | Requester pays |
|---|---|---|---|---|---|---|
| `sentinel-2-c1-l2a` | 29.9M | 2015-06 to present | 10/20/60 | 326xx (UTM) | `e84-earth-search-sentinel-data`, us-west-2, **HTTPS COGs** | No |
| `sentinel-2-l2a` | 50.9M | 2015-06 to present (legacy) | 10/20/60 | UTM | COG and `-jp2` assets | Not recorded |
| `sentinel-2-pre-c1-l2a` | 35k | frozen archive | 10/20/60 | UTM | same as c1 | Not recorded |
| `sentinel-2-l1c` | 44.3M | 2015-06 to present (TOA) | 10/20/60 | UTM | `s3://sentinel-s2-l1c` JP2 | Not recorded |
| `sentinel-1-grd` | 3.7M | 2014-10 to present | ~20x22 res / 10m px | 4326 | `s3://sentinel-s1-l1c` | **Yes** |
| `landsat-c2-l2` | 10.3M | 1982-08 to present | 30/60/100/120 | UTM | `s3://usgs-landsat` | **Yes** |
| `cop-dem-glo-30` | 26.4k | static 2021 | 30 | 4326 | `s3://copernicus-dem-30m` | No |
| `cop-dem-glo-90` | 26.5k | static 2021 | 90 | 4326 | `s3://copernicus-dem-90m` | No |
| `naip` | 1.4M | 2010 to 2022 (US only) | 0.6/1 | 269xx (NAD83) | `s3://naip-analytic` | **Yes** |

Platforms: Sentinel-2 = sentinel-2a/2b (msi); Sentinel-1 = sentinel-1a/1b/1c;
Landsat = landsat-4/5/7/8/9 (oli/tirs/tm/etm+); DEM = tandem-x; NAIP = aerial.

## 3. Item anatomy (per family)

Common top level: `id, bbox, geometry (Polygon), collection, properties,
assets, links, stac_version, stac_extensions`. Links carry
`self / canonical (s3) / via (originating archive) / parent / collection /
root / thumbnail` (+ `cite-as` DOI on Landsat).

### Sentinel-2 (c1-l2a, l2a, l1c)
- 23 assets (c1): 13 reflectance bands (B01-B12), `visual`, `preview`,
  `thumbnail`, `scl`, `aot`, `wvp`, `cloud`, `snow`, 3 XML/JSON metadata.
- `eo:cloud_cover`, `view:sun_elevation/azimuth`, `proj:epsg/centroid`,
  MGRS tiling (`mgrs:utm_zone/latitude_band/grid_square`).
- **Scene classification percentages** that may support water or flood analysis:
  `s2:water_percentage`, `s2:vegetation_percentage`, `s2:snow_ice_percentage`,
  `s2:high/medium_proba_clouds_percentage`, `s2:nodata_pixel_percentage`, etc.
- c1 assets: https COG hrefs, `gsd`, `proj:shape`, `proj:transform`,
  `raster:bands` (`uint16`, nodata 0, **scale 1e-4, offset -0.1**),
  `file:size`, and a bare-hex `file:checksum` (192-bit, **not** a valid
  SHA-256/multihash; do not emit it as `sha256`).
- l1c/l2a legacy assets are `s3://` or COG depending on variant.

### Sentinel-1 GRD
- 10-18 assets: `vv`/`vh` (or `hh`/`hv`) COG + calibration/noise/product
  XML schemas + `safe-manifest`, `thumbnail`. **All `s3://`, requester pays.**
- SAR properties: `sar:polarizations` ([VV,VH] standard), `sar:instrument_mode`
  (IW/EW/SM), `sar:frequency_band` (C), `sar:resolution_range/azimuth`,
  `sar:pixel_spacing_*`, `sar:observation_direction`.
- Orbit: `sat:orbit_state` (ascending/descending), `sat:relative_orbit`,
  `sat:absolute_orbit`, `s1:orbit_source` (POEORB/RESORB/PREORB),
  `s1:product_timeliness` (NRT-3h etc.), `s1:resolution` (high/medium/full).
- `start_datetime`/`end_datetime` (not point `datetime` alone);
  `proj:epsg` = 4326 with degree-unit `proj:transform`, `proj:shape` ~[26600,16686].
- No `eo:cloud_cover`; SAR observations are not blocked by cloud cover.

### Landsat C2 L2
- 25-28 assets: optical (coastal/blue/green/red/nir08/swir16/swir22),
  **thermal** (`lwir11`, kelvin, unit present), ST suite (`atran`, `cdist`,
  `drad`, `urad`, `trad`, `emis`, `emsd`), QA (`qa_pixel`, `qa_radsat`,
  `qa_aerosol`, `cloud_qa`), 3 metadata (`mtl.json/txt/xml`), browse.
  All `s3://usgs-landsat`, requester pays.
- Band naming differs from S2: `eo:bands[].name` = `TM_B1`-style;
  `common_name` holds `blue/green/red/...`.
- `landsat:wrs_path/row`, `landsat:cloud_cover_land`, `landsat:collection_category`,
  `landsat:scene_id`, `sci:doi`, `gsd` 30, `view:sun_elevation`, `proj:transform`.
- Scale factor: reflectance `raster:bands.scale` = 2.75e-05.

### Copernicus DEM
- Single `data` asset: float32 COG, unit `meter`, EPSG:4326, 3600x3600 tiles
  (1deg x 1deg), `proj:transform` in degrees. Static mosaic; datetime filters
  are meaningless (all items stamped 2021-04-22). No `eo:cloud_cover`.

### NAIP
- 2 assets: `image` (one COG containing **4 bands** Red/Green/Blue/NIR;
  `eo:bands` lists 4 entries on a single asset) and `metadata`.
  `s3://naip-analytic`, requester pays.
- `naip:state`, `naip:year`, `gsd` 0.6 or 1, US-only extent, irregular
  revisit (state-by-state cycles). No `eo:cloud_cover`.