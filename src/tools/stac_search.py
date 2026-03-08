"""Spatial STAC search — finds optical/radar scenes by bbox with temporal alignment."""
from datetime import datetime, timedelta
from pystac_client import Client


def search_satellite_data(catalog_config: dict, bbox: list, max_cloud_cover: float, modalities: list, limit: int = 1) -> dict:
    catalog = Client.open(catalog_config["url"])
    collections = catalog_config.get("collections", {})
    results = {}
    anchor_geom, anchor_dt = None, None

    if "optical" in modalities and collections.get("optical"):
        search = catalog.search(
            collections=[collections["optical"]], bbox=bbox,
            query={"eo:cloud_cover": {"lt": max_cloud_cover}}, max_items=limit
        )
        items = [item.to_dict() for item in search.items()]
        results["optical"] = items

        # Use first optical scene as anchor for temporal alignment
        if items:
            anchor_geom = items[0].get("geometry")
            dt_str = items[0].get("properties", {}).get("datetime", "")
            if dt_str:
                anchor_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))

    if "radar" in modalities and collections.get("radar"):
        search_params = {"collections": [collections["radar"]], "max_items": limit}
        if anchor_geom and anchor_dt:
            # Constrain radar to ±3 days of optical anchor
            start = (anchor_dt - timedelta(days=3)).strftime("%Y-%m-%d")
            end = (anchor_dt + timedelta(days=3)).strftime("%Y-%m-%d")
            search_params.update(intersects=anchor_geom, datetime=f"{start}/{end}")
        else:
            search_params["bbox"] = bbox

        results["radar"] = [item.to_dict() for item in catalog.search(**search_params).items()]

    if "elevation" in modalities and collections.get("elevation"):
        search_params = {"collections": [collections["elevation"]], "bbox": bbox, "max_items": limit}
        results["elevation"] = [item.to_dict() for item in catalog.search(**search_params).items()]

    return results
