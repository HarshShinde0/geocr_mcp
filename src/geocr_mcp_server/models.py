"""Pydantic models for the GeoCroissant MCP server responses."""

from pydantic import BaseModel, Field
from typing import Any


def _exclude_none(self: BaseModel, **kwargs: Any) -> dict[str, Any]:
    """Overrides model_dump to exclude None values by default."""
    kwargs.setdefault('exclude_none', True)
    return BaseModel.model_dump(self, **kwargs)


class ValidationReport(BaseModel):
    """Result of validating a Croissant/GeoCroissant document."""

    valid: bool = Field(description='Whether the document passed metadata validation.')
    source: str | None = Field(default=None, description='Where the document was loaded from.')
    dataset_name: str | None = Field(
        default=None,
        description='Dataset name extracted when the document is loadable.',
    )
    conforms_to: list[str] = Field(
        default_factory=list,
        description='Declared specification conformance targets.',
    )
    is_geospatial: bool = Field(
        default=False,
        description=(
            'True when the document declares GeoCroissant conformance '
            '(http://mlcommons.org/croissant/geo/...).'
        ),
    )
    errors: list[str] = Field(default_factory=list, description='Blocking validation errors.')
    warnings: list[str] = Field(
        default_factory=list, description='Non-blocking validation warnings.'
    )

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """See base class."""
        return _exclude_none(self, **kwargs)


class StructureGraph(BaseModel):
    """Nodes and edges of the Croissant structure graph."""

    node_count: int = Field(description='Number of nodes in the graph.')
    edge_count: int = Field(description='Number of edges in the graph.')
    nodes: list[dict[str, Any]] = Field(
        description='Graph nodes with @id, type and parent information.'
    )
    edges: list[dict[str, Any]] = Field(description='Directed edges (source @id -> target @id).')

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """See base class."""
        return _exclude_none(self, **kwargs)


class RecordsPreview(BaseModel):
    """First records materialized from a RecordSet."""

    record_set: str = Field(description='The RecordSet @id records were read from.')
    columns: list[str] = Field(description='Column names found across the records.')
    rows: list[dict[str, Any]] = Field(description='The materialized records.')
    num_records: int = Field(description='Number of records returned.')
    truncated: bool = Field(
        description=(
            'True when the preview reached the requested limit; additional records may exist.'
        )
    )

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """See base class."""
        return _exclude_none(self, **kwargs)


class DistributionUrls(BaseModel):
    """Source asset URIs extracted from a dataset distribution."""

    urls: list[dict[str, Any]] = Field(
        description=(
            'One entry per FileObject/FileSet: name, contentUrl(s), '
            'encodingFormat and hashes when declared.'
        )
    )
    count: int = Field(description='Number of returned distribution entries.')

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """See base class."""
        return _exclude_none(self, **kwargs)


class ScaffoldResult(BaseModel):
    """Result of generating a GeoCroissant JSON-LD scaffold."""

    valid: bool = Field(
        description='Whether the generated JSON-LD passes mlcroissant metadata validation.'
    )
    json_ld: dict[str, Any] = Field(description='The generated JSON-LD document.')
    errors: list[str] = Field(
        default_factory=list, description='Validation errors on the generated file.'
    )
    warnings: list[str] = Field(
        default_factory=list, description='Validation warnings on the generated file.'
    )
    path: str | None = Field(
        default=None, description='File path when the scaffold was written to disk.'
    )

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """See base class."""
        return _exclude_none(self, **kwargs)
