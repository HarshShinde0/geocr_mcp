"""Place-name resolution for EO spatial searches."""

import httpx
from typing import Any


NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
USER_AGENT = 'geocr-mcp/1.0 (https://github.com/HarshShinde0/geocr_mcp)'


def geocode_place(place_name: str, limit: int = 5) -> dict[str, Any]:
    """Resolves a place name to candidate WGS84 bounding boxes."""
    query = place_name.strip()
    if not query:
        raise ValueError('place_name must not be empty.')
    capped_limit = max(1, min(int(limit), 10))
    response = httpx.get(
        NOMINATIM_URL,
        params={
            'q': query,
            'format': 'jsonv2',
            'addressdetails': 1,
            'limit': capped_limit,
        },
        headers={'User-Agent': USER_AGENT},
        timeout=20.0,
    )
    response.raise_for_status()

    candidates = []
    for result in response.json():
        bounds = result.get('boundingbox') or []
        if len(bounds) != 4:  # pragma: no cover - malformed upstream response
            continue
        south, north, west, east = (float(value) for value in bounds)
        candidates.append(
            {
                'display_name': result.get('display_name'),
                'type': result.get('type'),
                'category': result.get('category'),
                'latitude': float(result['lat']),
                'longitude': float(result['lon']),
                'bbox': [west, south, east, north],
                'importance': result.get('importance'),
            }
        )
    return {
        'query': query,
        'count': len(candidates),
        'candidates': candidates,
        'attribution': 'OpenStreetMap contributors, Nominatim',
    }
