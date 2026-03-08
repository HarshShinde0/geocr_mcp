import yaml
from pathlib import Path


def load_config() -> dict:
    """Load config from catalogs.yaml."""
    path = Path(__file__).parent.parent / "config" / "catalogs.yaml"
    with open(path) as f:
        return yaml.safe_load(f)
