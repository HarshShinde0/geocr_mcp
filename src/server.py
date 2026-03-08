"""GeoCR MCP Server — thin data pipes, the AI writes all code."""
import json
import os
import asyncio
from mcp.server import Server
from mcp.types import Tool, TextContent

from src.config import load_config
from src.tools.stac_search import search_satellite_data
from src.tools.geocr_generator import generate_geocroissant_metadata

app = Server("geocr-mcp-server")

# Tool Definitions
def _tool(name, desc, props=None, required=None):
    """Shorthand to define a tool without repeating boilerplate."""
    schema = {"type": "object", "properties": props or {}}
    if required:
        schema["required"] = required
    return Tool(name=name, description=desc, inputSchema=schema)


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        _tool("search_datasets",
              "Search geospatial datasets by keyword (e.g. 'flood', 'wildfire'). Returns matching STAC collections.",
              {"query": {"type": "string", "description": "Search query"},
               "limit": {"type": "number", "description": "Max results (default 10)"}},
              ["query"]),

        _tool("search_geospatial_data",
              "Search STAC catalogs by bounding box for optical/radar satellite data.",
              {"bbox": {"type": "array", "items": {"type": "number"}, "description": "[min_lon, min_lat, max_lon, max_lat]"},
               "max_cloud_cover": {"type": "number", "description": "Max cloud cover %"},
               "modalities": {"type": "array", "items": {"type": "string"}, "description": "['optical', 'radar']"},
               "limit": {"type": "number", "description": "Number of scenes (default 1)"}},
              ["bbox", "max_cloud_cover", "modalities"]),

        _tool("generate_geocroissant",
              "Generate GeoCroissant JSON-LD metadata from STAC search results.",
              {"output_filename": {"type": "string", "description": "Output filename, e.g. 'dataset.json'"},
               "bbox": {"type": "array", "items": {"type": "number"}, "description": "[min_lon, min_lat, max_lon, max_lat]"},
               "modalities": {"type": "array", "items": {"type": "string"}, "description": "['optical', 'radar']"}},
              ["output_filename", "bbox", "modalities"]),

        _tool("serve_geocroissant",
              "Read and return a GeoCroissant JSON file's metadata, fields, and asset URLs.",
              {"json_path": {"type": "string", "description": "Path to GeoCroissant JSON file"}},
              ["json_path"]),

        _tool("validate_geocroissant",
              "Validate a Croissant JSON file against the MLCommons spec.",
              {"json_path": {"type": "string", "description": "Path to JSON file"}},
              ["json_path"]),

        _tool("get_stac_asset_urls",
              "Extract direct TIF URLs from a GeoCroissant JSON file.",
              {"json_path": {"type": "string", "description": "Path to JSON file"}},
              ["json_path"]),

        _tool("geocr_builder_context",
              "Coding guidance for the AI: how to use rasterio, build PyTorch Datasets, visualize RGB, download assets."),

        _tool("geocr_help", "Get help for the GeoCR MCP server."),
        _tool("geocr_ping", "Test server health."),
    ]


# ── Tool Handlers ─────────────────────────────────────────────────

def _text(msg):
    return [TextContent(type="text", text=msg)]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:

    if name == "search_datasets":
        from src.tools.dataset_search import search_by_keyword
        r = await asyncio.to_thread(search_by_keyword, arguments["query"], int(arguments.get("limit", 10)))
        out = [f"## Results for \"{r['query']}\" (topics: {', '.join(r['topics'])})\n"]
        for i, d in enumerate(r["datasets"], 1):
            modality = d.get('modality', 'Unknown')
            out.append(f"{i}. **{d['title']}** (`{d['id']}`) [{modality}] — {d['catalog']}\n   {d['description']}\n   Temporal: {' → '.join(d['temporal'])} | License: {d['license']}\n")
        return _text("\n".join(out) if r["datasets"] else "No matches found.")

    if name == "search_geospatial_data":
        config = load_config()
        r = await asyncio.to_thread(
            search_satellite_data, config["catalogs"]["default"],
            arguments["bbox"], arguments["max_cloud_cover"],
            arguments["modalities"], arguments.get("limit", 1)
        )
        lines = [f"- {mod}: {len(items)} scenes" for mod, items in r.items()]
        return _text("Search Results:\n" + "\n".join(lines))

    if name == "generate_geocroissant":
        config = load_config()
        stac = await asyncio.to_thread(
            search_satellite_data, config["catalogs"]["default"],
            arguments["bbox"], 20, arguments["modalities"], 1
        )
        path = await asyncio.to_thread(
            generate_geocroissant_metadata,
            os.path.join(os.getcwd(), "generated_datasets", arguments["output_filename"]),
            arguments["bbox"], arguments["modalities"], stac
        )
        return _text(f"✅ Generated: {path}")

    if name == "serve_geocroissant":
        try:
            with open(arguments["json_path"], encoding="utf-8") as f:
                ds = json.load(f)
            out = [f"## {ds.get('name', '?')}\n{ds.get('description', '')}\nTemporal: {ds.get('temporalCoverage', '?')}"]
            for d in ds.get("distribution", []):
                out.append(f"- **{d.get('name', '?')}**: {d.get('contentUrl', '?')}")
            for rs in ds.get("recordSet", []):
                fields = [f.get("name", "?") for f in rs.get("field", [])]
                out.append(f"\nRecord Set `{rs.get('@id', '?')}`: {len(rs.get('data', []))} records, fields: {fields}")
            return _text("\n".join(out))
        except Exception as e:
            return _text(f"❌ {e}")

    if name == "validate_geocroissant":
        from src.tools.validation import validate
        def _run():
            import sys
            old_out, old_err = sys.stdout, sys.stderr
            try:
                sys.stdout = sys.stderr = open(os.devnull, "w")
                with open(arguments["json_path"], encoding="utf-8") as f:
                    return validate(f.read())
            finally:
                sys.stdout.close(); sys.stderr.close()
                sys.stdout, sys.stderr = old_out, old_err
        try:
            results = await asyncio.to_thread(_run)
        except Exception as e:
            return _text(f"❌ Crashed: {e}")
        icons = {"pass": "✅", "warning": "⚠️", "error": "❌"}
        return _text("\n".join(f"{icons.get(s, '❓')} {name}\n{msg}" for name, _, msg, s in results))

    if name == "get_stac_asset_urls":
        try:
            with open(arguments["json_path"], encoding="utf-8") as f:
                ds = json.load(f)
            urls = [f"- [{d.get('name', '?')}] {d['contentUrl']}"
                    for d in ds.get("distribution", []) if d.get("contentUrl", "").startswith("http")]
            return _text("STAC URLs:\n" + "\n".join(urls) if urls else "No URLs found.")
        except Exception as e:
            return _text(f"❌ {e}")

    if name == "geocr_builder_context":
        return _text("""# GeoCroissant Builder Context
Use rasterio for all satellite imagery (COG/GeoTIFF), never PIL/cv2.

## Read a scene
```python
import rasterio, numpy as np, torch
with rasterio.open(url) as src:
    tensor = torch.from_numpy(np.nan_to_num(src.read())).float()
```

## RGB visualization
```python
import rasterio, numpy as np, matplotlib.pyplot as plt
with rasterio.open(url) as src:
    rgb = np.moveaxis(src.read([1,2,3]), 0, -1).astype(float)
for i in range(3):
    p2, p98 = np.percentile(rgb[:,:,i][rgb[:,:,i]>0], [2, 98])
    rgb[:,:,i] = np.clip((rgb[:,:,i]-p2)/(p98-p2)*255, 0, 255)
plt.imshow(rgb.astype(np.uint8)); plt.show()
```

## Download a COG locally
```python
import rasterio
with rasterio.open(url) as src:
    with rasterio.open("local.tif", "w", **src.profile) as dst:
        dst.write(src.read())
```

## PyTorch Dataset (read fields from JSON dynamically)
```python
import json, torch, rasterio, numpy as np
from torch.utils.data import Dataset

class GeoCroissantDataset(Dataset):
    def __init__(self, json_path):
        with open(json_path) as f:
            meta = json.load(f)
        rs = meta["recordSet"][0]
        self.records = rs["data"]
        self.fields = {f["name"]: f["dataType"] for f in rs["field"]}

    def __len__(self): return len(self.records)

    def __getitem__(self, idx):
        rec = self.records[idx]
        sample = {}
        for name, dtype in self.fields.items():
            val = rec.get(f"{list(rec)[0].split('/')[0]}/{name}")
            if dtype == "sc:URL" and val and val.startswith("http"):
                with rasterio.open(val) as src:
                    sample[name] = torch.from_numpy(np.nan_to_num(src.read())).float()
            else:
                sample[name] = val
        return sample
```""")

    if name == "geocr_help":
        return _text("""# GeoCR MCP Server
Thin tools for geospatial ML — the AI writes all code.

## Tools
1. `search_datasets` — keyword search (flood, wildfire, etc.)
2. `search_geospatial_data` — bbox spatial search
3. `generate_geocroissant` — create metadata JSON
4. `serve_geocroissant` — read back metadata
5. `validate_geocroissant` — validate against spec
6. `get_stac_asset_urls` — extract TIF URLs
7. `geocr_builder_context` — coding guidance (rasterio, PyTorch, RGB)
8. `geocr_ping` — health check

## Flow
search → generate → serve → validate → AI writes viz/download/training code""")

    if name == "geocr_ping":
        return _text("Pong! 🚀")

    raise ValueError(f"Unknown tool: {name}")
