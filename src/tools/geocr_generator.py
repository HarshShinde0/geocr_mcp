"""GeoCroissant metadata generator — builds JSON-LD from STAC results + skeleton template."""
import json
import hashlib
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


def generate_geocroissant_metadata(output_path: str, bbox: list, modalities: list, stac_results: dict) -> str:
    """Clone skeleton, inject STAC data, write JSON-LD."""
    # Load skeleton
    with open(TEMPLATE_DIR / "geocr_skeleton.json", encoding="utf-8") as f:
        dataset = json.load(f)

    # Extract metadata from all items
    all_items = stac_results.get("optical", []) + stac_results.get("radar", []) + stac_results.get("elevation", [])
    dates = [item["properties"]["datetime"] for item in all_items if item.get("properties", {}).get("datetime")]
    platforms = {item["properties"].get("platform") for item in all_items if item.get("properties", {}).get("platform")}

    if dates:
        dates.sort()
        dataset["temporalCoverage"] = f"{dates[0]}/{dates[-1]}"

    dataset["@id"] = f"geocr_{'-'.join(modalities)}_{dates[0][:10] if dates else 'unknown'}"
    dataset["name"] = f"GeoCroissant ({', '.join(platforms) if platforms else '+'.join(modalities)})"
    dataset["description"] = f"Multi-modal satellite dataset. BBox: {bbox}."
    dataset["spatialCoverage"] = {
        "@type": "Place",
        "geo": {"@type": "GeoShape", "box": f"{bbox[1]} {bbox[3]} {bbox[0]} {bbox[2]}"}
    }

    # Build distribution and inline records
    distribution, records = [], []
    optical = stac_results.get("optical", [])
    radar = stac_results.get("radar", [])
    elevation = stac_results.get("elevation", [])

    for i in range(max(len(optical), len(radar), len(elevation))):
        opt_href, rad_href, elev_href, dt = "", "", "", "unknown"

        if i < len(optical):
            assets = optical[i].get("assets", {})
            opt_href = (assets.get("visual") or assets.get("data") or next(iter(assets.values()), {})).get("href", "")
            dt = optical[i]["properties"].get("datetime", dt)
            distribution.append({
                "@type": "cr:FileObject", "@id": f"optical_{i}",
                "name": f"Optical {i}", "contentUrl": opt_href,
                "encodingFormat": "image/tiff; application=geotiff; profile=cloud-optimized",
                "sha256": hashlib.sha256(opt_href.encode()).hexdigest()
            })

        if i < len(radar):
            assets = radar[i].get("assets", {})
            rad_href = (assets.get("data") or next(iter(assets.values()), {})).get("href", "")
            if dt == "unknown":
                dt = radar[i]["properties"].get("datetime", dt)
            distribution.append({
                "@type": "cr:FileObject", "@id": f"radar_{i}",
                "name": f"Radar {i}", "contentUrl": rad_href,
                "encodingFormat": "image/tiff; application=geotiff; profile=cloud-optimized",
                "sha256": hashlib.sha256(rad_href.encode()).hexdigest()
            })

        if i < len(elevation):
            assets = elevation[i].get("assets", {})
            elev_href = (assets.get("data") or next(iter(assets.values()), {})).get("href", "")
            if dt == "unknown":
                dt = elevation[i]["properties"].get("datetime", dt)
            distribution.append({
                "@type": "cr:FileObject", "@id": f"elevation_{i}",
                "name": f"Elevation {i}", "contentUrl": elev_href,
                "encodingFormat": "image/tiff; application=geotiff; profile=cloud-optimized",
                "sha256": hashlib.sha256(elev_href.encode()).hexdigest()
            })

        records.append({
            "fused_acquisitions/id": i, "fused_acquisitions/datetime": dt,
            "fused_acquisitions/optical_image": opt_href, "fused_acquisitions/radar_image": rad_href,
            "fused_acquisitions/elevation_image": elev_href
        })

    dataset["distribution"] = distribution
    dataset["recordSet"] = [{
        "@type": "cr:RecordSet", "@id": "fused_acquisitions",
        "name": "Fused Acquisitions", "data": records,
        "field": [
            {"@type": "cr:Field", "@id": "fused_acquisitions/id", "name": "id", "dataType": "sc:Integer"},
            {"@type": "cr:Field", "@id": "fused_acquisitions/datetime", "name": "datetime", "dataType": "sc:DateTime"},
            {"@type": "cr:Field", "@id": "fused_acquisitions/optical_image", "name": "optical_image", "dataType": "sc:URL"},
            {"@type": "cr:Field", "@id": "fused_acquisitions/radar_image", "name": "radar_image", "dataType": "sc:URL"},
            {"@type": "cr:Field", "@id": "fused_acquisitions/elevation_image", "name": "elevation_image", "dataType": "sc:URL"},
        ]
    }]

    # Write
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)

    return str(out.absolute())
