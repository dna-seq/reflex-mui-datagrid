"""Polars-bio integration for reflex-mui-datagrid.

Requires the ``[bio]`` extra::

    pip install reflex-mui-datagrid[bio]

Provides convenience functions that automatically extract column
descriptions from polars-bio metadata (VCF headers, etc.) and feed
them into :func:`lazyframe_to_datagrid`.
"""

from typing import Any

import polars as pl
import polars_bio as pb

from reflex_mui_datagrid.models import ColumnDef
from reflex_mui_datagrid.polars_utils import lazyframe_to_datagrid

# ---------------------------------------------------------------------------
# Standard VCF column descriptions (defined by the VCF specification,
# not present in individual file headers).
# ---------------------------------------------------------------------------

VCF_STANDARD_DESCRIPTIONS: dict[str, str] = {
    "chrom": "Chromosome or contig name",
    "start": "Start position of the variant (1-based by default)",
    "end": "End position of the variant",
    "id": "Variant identifier (e.g. dbSNP rsID); '.' if unknown",
    "ref": "Reference allele bases",
    "alt": "Alternate allele bases (comma-separated if multiple)",
    "qual": "Phred-scaled quality score for the ALT assertion",
    "filter": "Filter status: PASS if the variant passed all filters",
}


def extract_vcf_descriptions(lf: pl.LazyFrame) -> dict[str, str]:
    """Extract column descriptions from a polars-bio VCF LazyFrame.

    Merges three sources of descriptions (later sources override earlier):

    1. Standard VCF specification column descriptions (chrom, start, etc.)
    2. INFO field descriptions from the VCF header
    3. FORMAT field descriptions from the VCF header

    Args:
        lf: A LazyFrame produced by ``polars_bio.scan_vcf()``.

    Returns:
        A flat ``{column_name: description}`` dict suitable for passing
        to :func:`lazyframe_to_datagrid` as ``column_descriptions``.
    """
    descriptions: dict[str, str] = dict(VCF_STANDARD_DESCRIPTIONS)

    metadata: dict[str, Any] = pb.get_metadata(lf)
    header: dict[str, Any] | None = metadata.get("header")
    if header is None:
        return descriptions

    # INFO fields: {"END": {"type": "Integer", "description": "...", ...}, ...}
    info_fields: dict[str, dict[str, Any]] = header.get("info_fields", {})
    for field_name, field_meta in info_fields.items():
        desc = field_meta.get("description")
        if desc:
            descriptions[field_name] = desc

    # FORMAT fields: {"GT": {"type": "String", "description": "...", ...}, ...}
    format_fields: dict[str, dict[str, Any]] = header.get("format_fields", {})
    for field_name, field_meta in format_fields.items():
        desc = field_meta.get("description")
        if desc:
            descriptions[field_name] = desc

    # FILTER descriptions (useful for display, keyed by filter ID)
    filters: list[dict[str, str]] = header.get("filters", [])
    filter_descs = [f"{f['id']}: {f['description']}" for f in filters if f.get("description")]
    if filter_descs:
        descriptions["filter"] = "Filter status. " + "; ".join(filter_descs)

    return descriptions


def bio_lazyframe_to_datagrid(
    lf: pl.LazyFrame,
    *,
    id_field: str | None = None,
    show_id_field: bool = False,
    limit: int | None = None,
    single_select_threshold: int = 20,
    single_select_ratio: float = 0.5,
    column_descriptions: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[ColumnDef]]:
    """Convert a polars-bio LazyFrame into MUI DataGrid rows and column defs.

    This is a convenience wrapper around :func:`lazyframe_to_datagrid` that
    automatically extracts column descriptions from polars-bio metadata
    (e.g. VCF INFO/FORMAT header fields).

    Any descriptions passed via *column_descriptions* override the
    automatically extracted ones.

    To show descriptions as subtitles in the column headers, pass
    ``show_description_in_header=True`` to the ``data_grid()`` component.

    Args:
        lf: A LazyFrame produced by ``polars_bio.scan_vcf()`` (or similar).
        id_field: Name of the column that serves as the unique row identifier.
        show_id_field: Whether to include the row identifier as a visible column.
        limit: Optional maximum number of rows to collect.
        single_select_threshold: Max distinct values for auto singleSelect.
        single_select_ratio: Max unique/row ratio for auto singleSelect.
        column_descriptions: Optional extra descriptions that override any
            automatically extracted ones.

    Returns:
        A ``(rows, column_defs)`` tuple ready for the DataGrid component.
    """
    # Start with auto-extracted descriptions, then let caller overrides win.
    merged_descriptions = extract_vcf_descriptions(lf)
    if column_descriptions is not None:
        merged_descriptions.update(column_descriptions)

    return lazyframe_to_datagrid(
        lf,
        id_field=id_field,
        show_id_field=show_id_field,
        limit=limit,
        single_select_threshold=single_select_threshold,
        single_select_ratio=single_select_ratio,
        column_descriptions=merged_descriptions,
    )
