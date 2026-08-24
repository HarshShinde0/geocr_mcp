"""Shared helpers for the GeoCroissant MCP server.

The configured ``mlcroissant`` package parses and validates Croissant
documents. This module resolves inputs and summarizes the resulting objects
for MCP responses.
"""

import datetime
import json
import os
import tempfile
from mlcroissant._src.structure_graph.nodes.field import Field
from mlcroissant._src.structure_graph.nodes.file_object import FileObject
from mlcroissant._src.structure_graph.nodes.file_set import FileSet
from mlcroissant._src.structure_graph.nodes.metadata import Metadata
from mlcroissant._src.structure_graph.nodes.record_set import RecordSet
from pathlib import Path
from typing import Any


JSONLD_EXTENSIONS = ('.json', '.jsonld')


def resolve_jsonld_input(
    jsonld_content: str | None = None,
    jsonld_path: str | None = None,
    jsonld_url: str | None = None,
) -> dict[str, Any] | str:
    """Resolves the user input into a valid `mlc.Dataset(jsonld=...)` argument.

    Priority: inline content > local path > URL. Exactly one source must be
    provided. Inline JSON content is parsed into a dict; paths and URLs are
    passed through as strings for `mlcroissant` to handle natively.
    """
    provided = [bool(v) for v in (jsonld_content, jsonld_path, jsonld_url)]
    if sum(provided) == 0:
        raise ValueError(
            'No input provided. Pass exactly one of: jsonld_content, jsonld_path or jsonld_url.'
        )
    if sum(provided) > 1:
        raise ValueError(
            'Multiple inputs provided. Pass exactly one of: jsonld_content, '
            'jsonld_path or jsonld_url.'
        )
    if jsonld_content:
        try:
            return json.loads(jsonld_content)
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(
                f'jsonld_content is not valid JSON: {e}', e.doc, e.pos
            ) from e
    if jsonld_path:
        path = Path(os.path.expanduser(jsonld_path)).resolve()
        if not path.is_file():
            raise FileNotFoundError(f'File not found: {path}')
        return str(path)
    return str(jsonld_url)


def load_dataset(jsonld: dict[str, Any] | str):
    """Loads a Croissant dataset via the `mlcroissant` library.

    Runs the full static analysis of the JSON-LD (structure graph + checks).
    Raises `mlcroissant.ValidationError` when the document is invalid.
    """
    # Imported lazily so that importing this module stays cheap.
    from mlcroissant import Dataset as MlcDataset

    return MlcDataset(jsonld=jsonld)


def node_type_name(node: Any) -> str:
    """Returns a human-readable type name for a structure-graph node."""
    mapping = [
        (Metadata, 'Metadata'),
        (FileObject, 'FileObject'),
        (FileSet, 'FileSet'),
        (RecordSet, 'RecordSet'),
        (Field, 'Field'),
    ]
    for cls, name in mapping:
        if isinstance(node, cls):
            return name
    return type(node).__name__


def _language_value(value: Any) -> Any:
    """Unboxes language-tagged values (`{'en': 'text'}` -> `'text'`)."""
    if isinstance(value, dict) and len(value) == 1:
        return next(iter(value.values()))
    return value


def to_json_safe(value: Any, max_depth: int = 8) -> Any:
    """Recursively converts library objects into JSON-serializable values."""
    if max_depth <= 0:
        return repr(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime.datetime):
        return from_datetime_to_str_safe(value)
    if isinstance(value, datetime.date):
        return value.isoformat()
    # rdflib.URIRef / Literal are str subclasses but keep them plain strings.
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, 'to_json') and not isinstance(value, dict):
        try:
            return to_json_safe(value.to_json(), max_depth=max_depth - 1)
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(k): to_json_safe(v, max_depth - 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_json_safe(v, max_depth - 1) for v in value]
    if hasattr(value, '__dict__'):
        return type(value).__name__
    return str(value)


def from_datetime_to_str_safe(date: datetime.datetime | None) -> str | None:
    """Serializes a datetime as an ISO string (None-safe)."""
    if date is None:
        return None
    return date.isoformat()


def summarize_quantitative(value: Any) -> dict[str, Any] | str | None:
    """Summarizes a geocr QuantitativeValue / text / dict property."""
    if value is None:
        return None
    if isinstance(value, (str, int, float)):
        return _language_value(value)
    if isinstance(value, dict):
        return to_json_safe(value)
    # Library node (QuantitativeValue): expose value + unitText.
    result: dict[str, Any] = {'@type': 'QuantitativeValue'}
    if getattr(value, 'value', None) is not None:
        result['value'] = value.value
    unit = getattr(value, 'unitText', None)
    if unit is not None:
        result['unitText'] = _language_value(unit)
    return result


def summarize_band_configuration(value: Any) -> dict[str, Any] | str | None:
    """Summarizes a geocr BandConfiguration (node, dict or text)."""
    if value is None:
        return None
    if isinstance(value, str):
        return _language_value(value)
    if isinstance(value, dict):
        return to_json_safe(value)
    result: dict[str, Any] = {'@type': 'BandConfiguration'}
    total_bands = getattr(value, 'total_bands', None)
    if total_bands is not None:
        result['totalBands'] = total_bands
    bands = getattr(value, 'band_names_list', None)
    if bands:
        result['bandNamesList'] = list(bands)
    return result


def summarize_spectral_bands(values: Any) -> list[dict[str, Any]] | None:
    """Summarizes a list of geocr SpectralBand entries."""
    if not values:
        return None
    result = []
    for band in values:
        if isinstance(band, dict):
            result.append(to_json_safe(band))
            continue
        entry: dict[str, Any] = {}
        name = getattr(band, 'name', None)
        if name is not None:
            entry['name'] = _language_value(name)
        center = getattr(band, 'center_wavelength', None)
        if center is not None:
            entry['centerWavelength'] = summarize_quantitative(center)
        width = getattr(band, 'bandwidth', None)
        if width is not None:
            entry['bandwidth'] = summarize_quantitative(width)
        result.append(entry)
    return result


def summarize_distribution(metadata: Metadata) -> list[dict[str, Any]]:
    """Summarizes the `distribution` (FileObjects and FileSets)."""
    result = []
    for entry in metadata.distribution:
        item: dict[str, Any] = {
            '@id': entry.uuid,
            '@type': node_type_name(entry),
            'name': _language_value(getattr(entry, 'name', '')) or entry.uuid,
        }
        description = getattr(entry, 'description', None)
        if description:
            item['description'] = _language_value(description)
        encoding_formats = getattr(entry, 'encoding_formats', None)
        if encoding_formats:
            item['encodingFormat'] = list(encoding_formats)
        if isinstance(entry, FileObject):
            content_url = getattr(entry, 'content_url', None)
            if content_url:
                item['contentUrl'] = str(content_url)
            for attr, key in (
                ('content_size', 'contentSize'),
                ('md5', 'md5'),
                ('sha256', 'sha256'),
            ):
                val = getattr(entry, attr, None)
                if val:
                    item[key] = str(val)
        if isinstance(entry, FileSet):
            includes = getattr(entry, 'includes', None)
            if includes:
                item['includes'] = list(includes)
        contained_in = getattr(entry, 'contained_in', None)
        if contained_in:
            refs = [c if isinstance(c, str) else getattr(c, 'uuid', None) for c in contained_in]
            refs = [r for r in refs if r]
            if refs:
                item['containedIn'] = refs
        result.append(item)
    return result


def summarize_field(field: Field) -> dict[str, Any]:
    """Summarizes a RecordSet Field including its source/transform chain."""
    item: dict[str, Any] = {
        '@id': field.uuid,
        'name': _language_value(getattr(field, 'name', '')) or field.uuid,
    }
    description = getattr(field, 'description', None)
    if description:
        item['description'] = _language_value(description)
    data_types = getattr(field, 'data_types', None) or []
    if data_types:
        item['dataType'] = sorted(str(dt) for dt in data_types)
    if getattr(field, 'is_array', None):
        item['isArray'] = True
        shape = getattr(field, 'array_shape', None)
        if shape:
            item['arrayShape'] = shape
    value = getattr(field, 'value', None)
    if value is not None:
        item['value'] = to_json_safe(value)
    source = getattr(field, 'source', None)
    if source and bool(source):
        item['source'] = to_json_safe(source.to_json())
    references = getattr(field, 'references', None)
    if references and bool(references):
        item['references'] = references.uuid
    sub_fields = getattr(field, 'sub_fields', None) or []
    if sub_fields:
        item['subField'] = [summarize_field(sf) for sf in sub_fields]
    band_config = getattr(field, 'band_configuration', None)
    if band_config is not None:
        item['bandConfiguration'] = summarize_band_configuration(band_config)
    spectral = getattr(field, 'spectral_band_metadata', None)
    spectral_summary = summarize_spectral_bands(spectral)
    if spectral_summary:
        item['spectralBandMetadata'] = spectral_summary
    return item


def summarize_record_set(record_set: RecordSet) -> dict[str, Any]:
    """Summarizes a RecordSet with its fields and geo properties."""
    fields = getattr(record_set, 'fields', None) or []
    data = getattr(record_set, 'data', None)
    examples = getattr(record_set, 'examples', None)
    item: dict[str, Any] = {
        '@id': record_set.uuid,
        'name': _language_value(getattr(record_set, 'name', '')) or record_set.uuid,
        'field_count': len(fields),
        'fields': [summarize_field(f) for f in fields],
    }
    description = getattr(record_set, 'description', None)
    if description:
        item['description'] = _language_value(description)
    key = getattr(record_set, 'key', None)
    if key:
        item['key'] = list(key)
    if getattr(record_set, 'is_enumeration', None):
        item['isEnumeration'] = True
    if data is not None:
        item['num_declared_records'] = len(data)
    if examples:
        item['num_examples'] = len(examples)
    spatial_resolution = getattr(record_set, 'spatial_resolution', None)
    if spatial_resolution is not None:
        item['spatialResolution'] = summarize_quantitative(spatial_resolution)
    temporal_resolution = getattr(record_set, 'temporal_resolution', None)
    if temporal_resolution is not None:
        item['temporalResolution'] = summarize_quantitative(temporal_resolution)
    spatial_index = getattr(record_set, 'spatial_index', None)
    if spatial_index is not None:
        item['spatialIndex'] = to_json_safe(spatial_index)
    time_series_index = getattr(record_set, 'time_series_index', None)
    if time_series_index is not None:
        item['timeSeriesIndex'] = (
            time_series_index
            if isinstance(time_series_index, str)
            else getattr(time_series_index, 'uuid', None)
        )
    return item


def summarize_metadata(metadata: Metadata) -> dict[str, Any]:
    """Builds a structured summary of a loaded Metadata node."""

    def _names(nodes: list[Any]) -> list[str]:
        names = []
        for node in nodes:
            name = _language_value(node.name) if getattr(node, 'name', '') else ''
            names.append(str(name or node.uuid))
        return names

    summary: dict[str, Any] = {
        'name': _language_value(metadata.name),
        'conformsTo': list(metadata.conforms_to or []),
        'version': metadata.version,
    }
    if metadata.description:
        summary['description'] = _language_value(metadata.description)
    if metadata.url:
        summary['url'] = str(metadata.url)
    if metadata.license:
        summary['license'] = [
            lic.uuid if hasattr(lic, 'uuid') else str(lic) for lic in metadata.license
        ]
    if metadata.cite_as:
        summary['citeAs'] = metadata.cite_as
    dates = {
        'dateCreated': metadata.date_created,
        'datePublished': metadata.date_published,
        'dateModified': metadata.date_modified,
    }
    date_summary = {k: from_datetime_to_str_safe(v) for k, v in dates.items() if v}
    if date_summary:
        summary.update(date_summary)
    if metadata.creators:
        summary['creator'] = _names(metadata.creators)
    if metadata.publisher:
        summary['publisher'] = _names(metadata.publisher)
    if metadata.keywords:
        summary['keywords'] = [_language_value(k) for k in metadata.keywords]
    if metadata.same_as:
        summary['sameAs'] = [str(sa) for sa in metadata.same_as]

    # --- GeoCroissant extension properties ---
    geo: dict[str, Any] = {}
    if metadata.coordinate_reference_system is not None:
        geo['coordinateReferenceSystem'] = to_json_safe(metadata.coordinate_reference_system)
    spatial_res = summarize_quantitative(metadata.spatial_resolution)
    if spatial_res is not None:
        geo['spatialResolution'] = spatial_res
    temporal_res = summarize_quantitative(metadata.temporal_resolution)
    if temporal_res is not None:
        geo['temporalResolution'] = temporal_res
    band_config = summarize_band_configuration(metadata.band_configuration)
    if band_config is not None:
        geo['bandConfiguration'] = band_config
    spectral = summarize_spectral_bands(metadata.spectral_band_metadata)
    if spectral:
        geo['spectralBandMetadata'] = spectral
    if metadata.record_endpoint is not None:
        geo['recordEndpoint'] = to_json_safe(metadata.record_endpoint)
    if metadata.spatial_index is not None:
        geo['spatialIndex'] = to_json_safe(metadata.spatial_index)
    if metadata.spatial_bias is not None:
        geo['spatialBias'] = to_json_safe(metadata.spatial_bias)
    if metadata.sampling_strategy is not None:
        geo['samplingStrategy'] = to_json_safe(metadata.sampling_strategy)
    mwc = metadata.multi_wavelength_configuration
    if mwc is not None:
        geo['multiWavelengthConfiguration'] = (
            to_json_safe(mwc)
            if isinstance(mwc, (dict, str))
            else {
                'channelList': list(getattr(mwc, 'channel_list', []) or []),
            }
        )
    sic = metadata.solar_instrument_characteristics
    if sic is not None:
        geo['solarInstrumentCharacteristics'] = (
            to_json_safe(sic)
            if isinstance(sic, (dict, str))
            else {
                'observatory': sic.observatory,
                'instrument': sic.instrument,
            }
        )
    if metadata.spatial_coverage is not None:
        geo['spatialCoverage'] = to_json_safe(metadata.spatial_coverage)
    if geo:
        summary['geospatial'] = geo

    # --- Distribution & record sets ---
    distribution = summarize_distribution(metadata)
    if distribution:
        summary['distribution'] = distribution
    summary['record_sets'] = [summarize_record_set(rs) for rs in metadata.record_sets]
    return summary


def secure_output_path(filename: str, output_dir: str | None = None) -> Path:
    """Resolves an output filename inside the configured output directory.

    The filename is reduced to its basename to prevent path traversal. When
    `output_dir` is not given, `GEOCR_OUTPUT_DIR` is used, falling back to a
    temporary directory.
    """
    safe_name = os.path.basename(filename.strip())
    if not safe_name:
        raise ValueError('Output filename must not be empty.')
    directory = Path(
        output_dir
        or os.environ.get('GEOCR_OUTPUT_DIR')
        or os.path.join(tempfile.gettempdir(), 'geocr-mcp')
    ).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    return directory / safe_name


def write_json_ld(data: dict[str, Any], path: Path) -> Path:
    """Writes JSON-LD to disk and returns the path."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')
    return path
