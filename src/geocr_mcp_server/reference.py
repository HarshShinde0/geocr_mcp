"""Static GeoCroissant reference documentation served through MCP."""

import json
from geocr_mcp_server.spec import official_context


TOPICS = ('overview', 'context', 'properties', 'rai', 'example', 'python-api', 'all')

_OVERVIEW = """# GeoCroissant Specification - Overview

GeoCroissant extends MLCommons Croissant with geospatial concepts for GeoAI and
Earth-observation (EO) datasets, integrated with the Croissant Responsible AI (RAI) specification.

## Namespaces
| Prefix | IRI | Description |
|---|---|---|
| sc | https://schema.org/ | schema.org namespace |
| cr | http://mlcommons.org/croissant/ | Croissant base namespace |
| geocr | http://mlcommons.org/croissant/geo/ | GeoCroissant extension namespace |
| rai | http://mlcommons.org/croissant/RAI/ | Croissant Responsible AI extension |
| dct | http://purl.org/dc/terms/ | Dublin Core terms |

## Conformance declaration (dataset level)
```json
"conformsTo": [
  "http://mlcommons.org/croissant/1.1",
  "http://mlcommons.org/croissant/geo/1.0"
]
```
*(Add `"http://mlcommons.org/croissant/RAI/1.0"` when Responsible AI metadata is declared)*

## Core structure
A Croissant document describes:
- **Metadata** - name, description, license, creators, version...
- **distribution** - `cr:FileObject` (one source file: contentUrl plus
  md5/sha256 checksums) or `cr:FileSet` (files matching glob patterns inside a
  container archive).
- **recordSet** - collections of records; each declares **cr:Field** columns
  whose `source` extracts data from the distribution via `extract` (column,
  fileProperty, jsonPath) plus optional `transform` (regex, separator,
  format...). Fields can reference other fields (`references`) to express joins.

## Recommended tool workflow
1. `create_geocroissant_scaffold` - generate a starting document.
2. Edit the returned JSON-LD for domain specifics.
3. `validate_croissant` - check the edited metadata.
4. `inspect_geocroissant` / `get_structure_graph` - review the result.
5. `get_records_preview` - preview records from the selected RecordSet.
"""

_PROPERTIES = """# GeoCroissant Properties Reference

## Dataset-level properties (domain: sc:Dataset)
| Property | Expected type | Cardinality | Notes |
|---|---|---|---|
| geocr:coordinateReferenceSystem | sc:Text (e.g. "EPSG:4326") | ONE | CRS/projection of spatial data |
| geocr:spatialResolution | sc:Text or sc:QuantitativeValue | ONE | Ground sampling distance; also allowed on cr:RecordSet |
| geocr:temporalResolution | sc:Text or sc:QuantitativeValue | ZERO or ONE | Revisit cadence; also allowed on cr:RecordSet |
| geocr:bandConfiguration | geocr:BandConfiguration | ONE | Band layout; domains: sc:Dataset AND cr:Field |
| geocr:spectralBandMetadata | geocr:SpectralBand | MANY | Per-band wavelength info; domains: sc:Dataset AND cr:Field |
| geocr:recordEndpoint | sc:Text / sc:URL | ZERO or ONE | API endpoint serving records programmatically |
| geocr:spatialIndex | sc:Text | MANY | Precomputed index tokens (H3/DGGS/geohash); domains: sc:Dataset, cr:RecordSet |
| geocr:spatialBias | sc:Text | ZERO or ONE | Spatial representativeness limitations (Responsible AI) |
| geocr:samplingStrategy | sc:Text | ZERO or ONE | How samples were selected (Responsible AI) |
| geocr:multiWavelengthConfiguration | geocr:MultiWavelengthConfiguration | ZERO or ONE | Space weather channel configuration |
| geocr:solarInstrumentCharacteristics | geocr:SolarInstrumentCharacteristics | ZERO or ONE | Observatory/instrument identifiers |

## Specialized types
- **geocr:BandConfiguration**: `geocr:totalBands` (sc:Integer, ONE) +
  `geocr:bandNamesList` (sc:Text, MANY).
- **geocr:SpectralBand**: name (sc:Text) + `geocr:centerWavelength`
  (QuantitativeValue, ONE) + `geocr:bandwidth` (QuantitativeValue, ZERO or ONE).
- **geocr:MultiWavelengthConfiguration**: `geocr:channelList` (sc:Text, MANY).
- **geocr:SolarInstrumentCharacteristics**: `geocr:observatory` +
  `geocr:instrument` (both sc:Text).
- **geocr:timeSeriesIndex** (domain: cr:RecordSet): Field used to index
  observations in a time series.

## Field-level properties (cr:Field)
- geocr:bandConfiguration and geocr:spectralBandMetadata attach band semantics
  to individual image fields.
- Use `cr:isArray: true` with `cr:arrayShape` like "512,512,6" for multi-band
  rasters (-1 marks unknown dimensions).

## Spatial / temporal coverage (schema.org)
```json
"spatialCoverage": {
  "@type": "Place",
  "geo": {"@type": "GeoShape", "box": "minLat minLon maxLat maxLon"}
},
"temporalCoverage": "2018-01-01/2021-12-31"
```
Note the lat-first ordering inside the GeoShape box per specification.
"""


def _context_doc() -> str:
    context = json.dumps(official_context(), indent=2)
    return (
        '# Server @context\n\n'
        'The server uses this Croissant context '
        'extended with the `geocr` prefix):\n\n```json\n' + context + '\n```\n'
    )


_EXAMPLE = """# Condensed Sample Document

HLS Burn Scars structure adapted from docs/croissant-geo-spec.md:

```json
{
  "@type": "Dataset",
  "name": "GeoCroissant Example: HLS Burn Scars",
  "conformsTo": [
    "http://mlcommons.org/croissant/1.1",
    "http://mlcommons.org/croissant/geo/1.0"
  ],
  "license": "https://creativecommons.org/licenses/by/4.0/",
  "spatialCoverage": {
    "@type": "Place",
    "geo": {"@type": "GeoShape", "box": "24.0 -125.0 49.0 -66.0"}
  },
  "temporalCoverage": "2018-01-01/2021-12-31",
  "geocr:coordinateReferenceSystem": "EPSG:4326",
  "geocr:spatialResolution": {"@type": "QuantitativeValue", "value": 30, "unitText": "m"},
  "geocr:bandConfiguration": {
    "@type": "geocr:BandConfiguration",
    "geocr:totalBands": 6,
    "geocr:bandNamesList": ["Blue", "Green", "Red", "NIR", "SW1", "SW2"]
  },
  "distribution": [
    {
      "@type": "cr:FileSet",
      "@id": "images",
      "name": "Images",
      "encodingFormat": "image/tiff",
      "includes": "images/**/*.tif"
    }
  ],
  "recordSet": [
    {
      "@type": "cr:RecordSet",
      "@id": "images_recordset",
      "name": "Images",
      "key": {"@id": "images_recordset/image"},
      "field": [
        {
          "@type": "cr:Field",
          "@id": "images_recordset/image",
          "name": "image",
          "dataType": "sc:ImageObject",
          "source": {
            "fileSet": {"@id": "images"},
            "extract": {"fileProperty": "content"}
          },
          "isArray": true,
          "arrayShape": "512,512,6"
        }
      ]
    }
  ]
}
```

Generate a document including @context with
`create_geocroissant_scaffold`.
"""

_PYTHON_API = """# mlcroissant Python API Cheat Sheet

Install (the fork carries core + GeoCroissant support):
```bash
pip install git+https://github.com/HarshShinde0/croissant.git@main#subdirectory=python/mlcroissant
```

## Load & validate
```python
import mlcroissant as mlc

dataset = mlc.Dataset(jsonld="metadata.json")   # path, URL or dict
# Raises mlc.ValidationError with a readable report when invalid.
print(dataset.metadata.name)
print(dataset.metadata.conforms_to)
```

## Iterate records
```python
for record in dataset.records(record_set="my_recordset"):
    print(record)   # dict keyed by fully-qualified field ids

# With a split filter (fields extracted via regex transforms):
for record in dataset.records(
    record_set="my_recordset",
    filters={"my_recordset/split": "train"},
):
    ...
```

## Inspect metadata objects
```python
md = dataset.metadata
md.file_objects     # [FileObject(content_url=..., sha256=...)]
md.file_sets        # [FileSet(includes=[...], contained_in=[...])]
md.record_sets      # [RecordSet(fields=[Field(...)])]
graph = md.ctx.graph           # networkx MultiDiGraph of the dataset
for node in graph.nodes:       # Metadata/FileObject/FileSet/RecordSet/Field
    print(node.uuid, type(node).__name__)
for u, v in graph.edges:
    print(u.uuid, '->', v.uuid)
json_ld = md.to_json()         # serialize metadata back to JSON-LD
```

## GeoCroissant node classes
```python
from mlcroissant import (
    BandConfiguration, SpectralBand, QuantitativeValue,
    MultiWavelengthConfiguration, SolarInstrumentCharacteristics,
)
bands = BandConfiguration(total_bands=6,
                          band_names_list=["Blue", "Green", "Red", "NIR", "SW1", "SW2"])
blue = SpectralBand(name="Blue",
                    center_wavelength=QuantitativeValue(value=490, unitText="nm"))
```
"""


_RAI = """# Responsible AI (RAI) Specification Reference

GeoCroissant integrates the official MLCommons Croissant Responsible AI (RAI) specification
(`http://mlcommons.org/croissant/RAI/`) and GeoCroissant geographic RAI extensions
(`http://mlcommons.org/croissant/geo/`).

## Complete A to Z Responsible AI Properties Catalog

| Property | Namespace / IRI | Expected Type | Cardinality | Pillar | Description |
|---|---|---|---|---|---|
| rai:annotationsPerItem | http://mlcommons.org/croissant/RAI/ | sc:Text | ONE | Labeling | Number or distribution of human labels/ratings per instance |
| rai:annotatorDemographics | http://mlcommons.org/croissant/RAI/ | sc:Text | MANY | Labeling | Socio-demographic specifications of annotators/curators |
| rai:dataAnnotationAnalysis | http://mlcommons.org/croissant/RAI/ | sc:Text | MANY | Labeling | Methods for analyzing disagreements or uncertainty signals |
| rai:dataAnnotationPlatform | http://mlcommons.org/croissant/RAI/ | sc:Text | MANY | Labeling | Platforms or tools used by human annotators |
| rai:dataAnnotationProtocol | http://mlcommons.org/croissant/RAI/ | sc:Text | MANY | Labeling | Instructions and guidelines for annotation workforce |
| rai:dataBiases | http://mlcommons.org/croissant/RAI/ | sc:Text | MANY | Safety & Bias | Imbalances, skews, or historical biases in the data |
| rai:dataCollection | http://mlcommons.org/croissant/RAI/ | sc:Text | ONE | Provenance | Key stages and methodology of the data collection process |
| rai:dataCollectionMissingData | http://mlcommons.org/croissant/RAI/ | sc:Text | ONE | Provenance | Data uncollected, missing, or dropped during acquisition |
| rai:dataCollectionRawData | http://mlcommons.org/croissant/RAI/ | sc:Text | ONE | Provenance | Description of source raw data before preprocessing |
| rai:dataCollectionTimeFrame | http://mlcommons.org/croissant/RAI/ | sc:Date / sc:DateTime | MANY | Provenance | Date/time range when data was observed/collected |
| rai:dataCollectionType | http://mlcommons.org/croissant/RAI/ | sc:Text | MANY | Provenance | Collection modality (Direct measurement, Web API, etc.) |
| rai:dataImputationProtocol | http://mlcommons.org/croissant/RAI/ | sc:Text | ONE | Provenance | Algorithms used to fill missing values or dropped pixels |
| rai:dataLimitations | http://mlcommons.org/croissant/RAI/ | sc:Text | MANY | Safety & Bias | Known data generalization limits and quality issues |
| rai:dataDataManipulationProtocol | http://mlcommons.org/croissant/RAI/ | sc:Text | ONE | Provenance | Data transformations, reprojections, or filtering |
| rai:dataPreprocessingProtocol | http://mlcommons.org/croissant/RAI/ | sc:Text | MANY | Provenance | Preprocessing steps (calibration, scaling, noise removal) |
| rai:dataReleaseMaintenancePlan | http://mlcommons.org/croissant/RAI/ | sc:Text | ONE | Impact | Versioning cadence and dataset maintenance policy |
| rai:dataSocialImpact | http://mlcommons.org/croissant/RAI/ | sc:Text | ONE | Impact | Societal benefits, potential harms, and ethical risks |
| rai:dataUseCases | http://mlcommons.org/croissant/RAI/ | sc:Text | MANY | Impact | Intended, authorized, and benchmark use cases |
| rai:hasSyntheticData | http://mlcommons.org/croissant/RAI/ | sc:Boolean | ONE | Safety & Bias | Declaration whether the dataset contains synthetic data |
| rai:machineAnnotationTools | http://mlcommons.org/croissant/RAI/ | sc:Text | MANY | Labeling | Software or AI models used in automated data labeling |
| rai:personalSensitiveInformation | http://mlcommons.org/croissant/RAI/ | sc:Text | MANY | Safety & Bias | Declarations regarding PII presence or absence |
| geocr:samplingStrategy | http://mlcommons.org/croissant/geo/ | sc:Text | ONE | Safety & Bias | Geographic/temporal sampling protocol (GeoCroissant RAI) |
| geocr:spatialBias | http://mlcommons.org/croissant/geo/ | sc:Text | ONE | Safety & Bias | Spatial representativeness limitations (GeoCroissant RAI) |

## Conformance Declaration
```json
"conformsTo": [
  "http://mlcommons.org/croissant/1.1",
  "http://mlcommons.org/croissant/geo/1.0",
  "http://mlcommons.org/croissant/RAI/1.0"
]
```

## Generating Responsible AI Metadata via MCP
All RAI properties are generated on demand via MCP tools rather than hardcoded. Specify arguments in `create_geocroissant_scaffold`, `create_geocroissant_from_stac`, or `create_geocroissant_from_stac_sources`:
- `spatial_bias`: Description of geographic limitations or domain boundaries
- `sampling_strategy`: Description of scene selection, cadence, or query filters
- `data_biases`: Imbalances or acquisition biases (e.g. cloud-free optical bias)
- `data_limitations`: Generalization limits, cloud/atmospheric occlusion, sensor noise
- `data_use_cases`: Intended, authorized, and benchmark applications
- `data_social_impact`: Anticipated positive impacts and risk mitigation
- `personal_sensitive_information`: Declarations regarding PII presence or absence
- `has_synthetic_data`: Boolean flag indicating if dataset contains synthetic data
- `data_collection`: Description of data collection protocol or source archive
- `rai_properties`: Dictionary of additional Croissant RAI properties (e.g. `prov:wasGeneratedBy`)

When any RAI parameter is provided, `http://mlcommons.org/croissant/RAI/1.0` is dynamically added to `conformsTo`.
"""


def render_reference(topic: str = 'all') -> str:
    """Renders the reference documentation for a given topic."""
    parts = {
        'overview': _OVERVIEW,
        'properties': _PROPERTIES,
        'rai': _RAI,
        'context': _context_doc(),
        'example': _EXAMPLE,
        'python-api': _PYTHON_API,
    }
    if topic == 'all':
        return '\n\n---\n\n'.join(
            parts[key] for key in ('overview', 'context', 'properties', 'rai', 'example', 'python-api')
        )
    return parts[topic]
