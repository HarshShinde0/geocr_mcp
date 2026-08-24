"""Data-driven STAC catalog registry.

The registry lives in ``config/catalogs.yaml``, shipped as package data. Set the
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

    normalized_catalogs: dict[str, dict[str, Any]] = {}
    for cid, cat in catalogs.items():
        if not isinstance(cat, dict) or not cat.get('url'):
            raise ValueError(f'Catalog `{cid}` is missing a `url`.')
        normalized_id = str(cid).strip().lower()
        if not normalized_id:
            raise ValueError('Catalog ids must not be empty.')
        cat.setdefault('name', cid)
        cat.setdefault('description', '')
        cat.setdefault('collections', [])
        configured_collections = cat.get('collections') or []
        if not isinstance(configured_collections, list):
            raise ValueError(
                f'Catalog `{normalized_id}` collections must be a list.'
            )
        if any(not isinstance(coll, str) or not coll.strip() for coll in configured_collections):
            raise ValueError(
                f'Catalog `{normalized_id}` collections must contain non-empty strings.'
            )
        if len(configured_collections) != len(set(configured_collections)):
            raise ValueError(f'Catalog `{normalized_id}` collections must be unique.')
        normalized_catalogs[normalized_id] = cat

    default_catalog = str(data.get('default_catalog') or '').strip().lower()
    if not default_catalog:
        default_catalog = next(iter(normalized_catalogs))
    if default_catalog not in normalized_catalogs:
        raise ValueError(
            f'Default catalog `{default_catalog}` is not defined in `catalogs`.'
        )

    return {
        'default_catalog': default_catalog,
        'catalogs': normalized_catalogs,
    }


def reload_config() -> None:
    """Clears the cached config so the next access re-reads the YAML."""
    get_config.cache_clear()


def get_catalog(catalog_id: str | None = None) -> dict[str, Any]:
    """Returns catalog metadata (with `id`) or raises ValueError if unknown."""
    config = get_config()
    registered = config['catalogs']
    cid = (catalog_id or config['default_catalog']).strip().lower()
    cat = registered.get(cid)
    if cat is None:
        raise ValueError(
            f'Unknown catalog "{catalog_id}". Available catalogs: {sorted(registered)}.'
        )
    return {'id': cid, **cat}


def list_catalogs() -> list[dict[str, Any]]:
    """Lists all registered STAC catalogs."""
    catalogs = get_config()['catalogs']
    return [
        {
            'id': cid,
            'name': cat['name'],
            'url': cat['url'],
            'description': cat['description'],
            'collection_discovery': 'live',
            'configured_collection_count': len(cat['collections']),
        }
        for cid, cat in sorted(catalogs.items())
    ]

