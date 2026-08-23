"""Data-driven STAC catalog registry.

The registry (catalogs, modalities and keyword heuristics) lives in
``config/catalogs.yaml``, shipped as package data. Set the
``GEOCR_CATALOGS_CONFIG`` environment variable to an alternate YAML file to
register your own catalogs without changing code. The parsed config is cached
after first load; call :func:`reload_config` to pick up changes.
"""

import os
import yaml
from functools import lru_cache
from importlib import resources
from loguru import logger
from typing import Any


CONFIG_ENV_VAR = 'GEOCR_CATALOGS_CONFIG'
_PACKAGE_CONFIG = ('config', 'catalogs.yaml')


def _read_config_text() -> str:
    """Reads the catalog YAML from the env override or shipped package data."""
    override = os.getenv(CONFIG_ENV_VAR)
    if override:
        logger.info(f'Loading catalog registry from {CONFIG_ENV_VAR}={override}')
        with open(override, encoding='utf-8') as handle:
            return handle.read()
    package, filename = _PACKAGE_CONFIG
    return (
        resources.files('geocr_mcp_server')
        .joinpath(package)
        .joinpath(filename)
        .read_text(encoding='utf-8')
    )



@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    """Returns the parsed, validated catalog registry (cached)."""
    try:
        data = yaml.safe_load(_read_config_text()) or {}
    except yaml.YAMLError as e:
        raise ValueError(f'Invalid YAML in catalog config: {e}') from e
    if not isinstance(data, dict):
        raise ValueError('Catalog config must be a YAML mapping.')

    catalogs = data.get('catalogs')
    if not isinstance(catalogs, dict) or not catalogs:
        raise ValueError('Catalog config must define a non-empty `catalogs` mapping.')

    modalities = tuple(data.get('modalities') or ())
    if not modalities:
        raise ValueError('Catalog config must define a non-empty `modalities` list.')

    for cid, cat in catalogs.items():
        if not isinstance(cat, dict) or not cat.get('url'):
            raise ValueError(f'Catalog `{cid}` is missing a `url`.')
        cat.setdefault('name', cid)
        cat.setdefault('description', '')
        cat.setdefault('common', {})

    topics = data.get('topics') or {}
    if not isinstance(topics, dict):
        raise ValueError('Catalog config `topics` must be a mapping.')
    known_collections = {
        coll
        for cat in catalogs.values()
        for colls in (cat.get('common') or {}).values()
        for coll in colls or []
    }
    for topic, colls in topics.items():
        if not isinstance(colls, list) or not colls:
            raise ValueError(f'Topic `{topic}` must map to a non-empty list.')
        unknown = [c for c in colls if c not in known_collections]
        if unknown:
            raise ValueError(
                f'Topic `{topic}` references collections missing from every '
                f"catalog's `common` lists: {unknown}."
            )

    return {
        'modalities': modalities,
        'default_cloud_cover': float(data.get('default_cloud_cover', 20.0)),
        'modality_hints': tuple(
            (modality, tuple(hints or ()))
            for modality, hints in (data.get('modality_hints') or {}).items()
        ),
        'topics': {str(t).strip().lower(): list(colls) for t, colls in topics.items()},
        'catalogs': {str(cid).strip().lower(): cat for cid, cat in catalogs.items()},
    }


def reload_config() -> None:
    """Clears the cached config so the next access re-reads the YAML."""
    get_config.cache_clear()


def modalities() -> tuple[str, ...]:
    """Returns the tuple of known sensor modalities."""
    return get_config()['modalities']


def default_cloud_cover() -> float:
    """Returns the default max cloud cover (%) for scene searches."""
    return get_config()['default_cloud_cover']


def modality_hints() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Returns ordered (modality, keyword-hints) pairs for classification."""
    return get_config()['modality_hints']


def topics() -> dict[str, list[str]]:
    """Returns the theme -> collections mapping from the registry."""
    return get_config()['topics']


def get_catalog(catalog_id: str) -> dict[str, Any]:
    """Returns catalog metadata (with `id`) or raises ValueError if unknown."""
    catalogs = get_config()['catalogs']
    cid = (catalog_id or '').strip().lower()
    cat = catalogs.get(cid)
    if cat is None:
        raise ValueError(
            f'Unknown catalog "{catalog_id}". Available catalogs: {sorted(catalogs)}.'
        )
    return {'id': cid, **cat}


def list_catalogs() -> list[dict[str, Any]]:
    """Lists all registered STAC catalogs with their modalities."""
    catalogs = get_config()['catalogs']
    return [
        {
            'id': cid,
            'name': cat['name'],
            'url': cat['url'],
            'description': cat['description'],
            'modalities': sorted(cat['common'].keys()),
            'common_collections': cat['common'],
        }
        for cid, cat in sorted(catalogs.items())
    ]


def static_collections() -> set[str]:
    """Returns collection ids of static datasets (e.g. elevation models)."""
    config = get_config()
    return {
        coll
        for cat in config['catalogs'].values()
        for coll in (cat.get('common') or {}).get('elevation', [])
    }

