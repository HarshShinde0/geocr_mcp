"""Keyword search — matches topics from YAML config to STAC collections."""
from pystac_client import Client
from src.config import load_config


def search_by_keyword(query: str, limit: int = 10) -> dict:
    config = load_config()
    catalogs = config["catalogs"]["search_catalogs"]
    topic_map = config.get("topics", {})
    query_lower = query.lower()

    # 1. Gather all collections matching the query topics
    themes = {}
    modalities = {}
    modality_keywords = {"optical", "radar", "sar", "elevation", "dem", "aerial"}

    for topic, colls in topic_map.items():
        if topic in query_lower:
            if topic in modality_keywords:
                modalities[topic] = set(colls)
            else:
                themes[topic] = set(colls)

    matched = set()
    topics = list(themes.keys()) + list(modalities.keys())
    
    theme_colls = set().union(*themes.values()) if themes else set()
    mod_colls = set().union(*modalities.values()) if modalities else set()
    
    # 2. Filter modalities logically depending on what user asked
    if themes and modalities:
        # e.g., "wildfire optical" -> fetch only optical datasets for wildfire
        intersection = theme_colls.intersection(mod_colls)
        matched = intersection if intersection else (theme_colls | mod_colls)
    elif themes:
        matched = theme_colls
    elif modalities:
        matched = mod_colls

    # Default fallback if nothing matches
    if not matched:
        matched = set(topic_map.get("multimodal", ["sentinel-2-l2a", "sentinel-1-grd"]))
        topics = ["general"]

    # 3. Helper to display dataset primary modality to the user
    def identify_modality(cid):
        for mod in ["optical", "radar", "sar", "elevation", "dem", "aerial"]:
            if cid in topic_map.get(mod, []):
                return mod.capitalize()
        return "Other"

    # 4. Fetch collection metadata explicitly (fast O(1) lookups)
    results = []
    for cat in catalogs:
        try:
            catalog_client = Client.open(cat["url"])
            for cid in sorted(list(matched)):
                if len(results) >= limit:
                    break
                try:
                    coll = catalog_client.get_collection(cid)
                    if coll:
                        ext = coll.extent
                        temporal = []
                        if ext and ext.temporal and ext.temporal.intervals:
                            temporal = [str(t) for t in ext.temporal.intervals[0]]
                        results.append({
                            "id": coll.id,
                            "title": coll.title or coll.id,
                            "description": (coll.description or "")[:200],
                            "catalog": cat["name"],
                            "modality": identify_modality(coll.id),
                            "temporal": temporal,
                            "license": coll.license or "proprietary",
                        })
                except Exception:
                    pass  # Collection might not exist in this catalog, normal
        except Exception:
            pass

    return {"query": query, "topics": topics, "datasets": results[:limit]}
