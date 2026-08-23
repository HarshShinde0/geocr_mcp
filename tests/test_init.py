"""Unit tests for geocr_mcp_server package metadata."""

import re
from geocr_mcp_server import MCP_SERVER_VERSION, __version__
from pathlib import Path


_PYPROJECT = Path(__file__).resolve().parents[1] / 'pyproject.toml'


def _pyproject_field(field: str) -> str:
    match = re.search(rf'^{field} = "(.+)"$', _PYPROJECT.read_text(), re.M)
    assert match, f'{field} not found in pyproject.toml'
    return match.group(1)


def test_version_exports():
    """The package exports matching version constants."""
    assert __version__ == MCP_SERVER_VERSION
    assert isinstance(__version__, str)
    assert __version__.count('.') == 2


def test_version_matches_pyproject():
    """The declared version matches pyproject.toml."""
    assert _pyproject_field('version') == __version__


def test_direct_reference_dependency():
    """Mlcroissant is pinned to the GeoCroissant fork via a direct URL."""
    text = _PYPROJECT.read_text()
    assert (
        'git+https://github.com/HarshShinde0/croissant.git@main'
        '#subdirectory=python/mlcroissant' in text
    )
