"""Utilities for converting polars LazyFrames to MUI X DataGrid rows and columns."""

from typing import Any

import polars as pl

from reflex_mui_datagrid.models import ColumnDef


def polars_dtype_to_grid_type(dtype: pl.DataType) -> str:
    """Map a polars DataType to the closest MUI DataGrid column type.

    Uses polars' built-in type-checking helpers for robustness across
    polars versions.

    Args:
        dtype: A polars data type.

    Returns:
        One of ``"string"``, ``"number"``, ``"boolean"``, ``"date"``,
        ``"dateTime"``.
    """
    if isinstance(dtype, pl.Boolean):
        return "boolean"
    if dtype.is_numeric():
        return "number"
    if isinstance(dtype, pl.Date):
        return "date"
    if isinstance(dtype, pl.Datetime):
        return "dateTime"
    # Everything else (String, Categorical, Enum, List, Struct, Duration, …)
    return "string"


def _humanize_field_name(field: str) -> str:
    """Convert a snake_case or raw field name to a human-friendly header.

    Examples:
        ``"first_name"`` -> ``"First Name"``
        ``"age"`` -> ``"Age"``
        ``"__row_id__"`` -> ``"Row Id"``
    """
    return field.strip("_").replace("_", " ").title()


def lazyframe_to_datagrid(
    lf: pl.LazyFrame,
    *,
    id_field: str | None = None,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], list[ColumnDef]]:
    """Convert a polars LazyFrame into MUI DataGrid *rows* and *column_defs*.

    Args:
        lf: The polars LazyFrame to convert.
        id_field: Name of the column that serves as the unique row identifier.
            If ``None`` and no ``"id"`` column exists, a ``"__row_id__"``
            column is added automatically with a zero-based row index.
        limit: Optional maximum number of rows to collect.

    Returns:
        A ``(rows, column_defs)`` tuple where *rows* is a list of dicts
        ready for the DataGrid ``rows`` prop, and *column_defs* is a list of
        :class:`ColumnDef` instances inferred from the schema.
    """
    if limit is not None:
        lf = lf.head(limit)

    df = lf.collect()

    # Ensure every row has an id MUI DataGrid can use.
    effective_id_field = id_field
    if effective_id_field is None and "id" not in df.columns:
        df = df.with_row_index("__row_id__")
        effective_id_field = "__row_id__"
    elif effective_id_field is None:
        effective_id_field = "id"

    # Build rows – serialise to Python dicts.
    # Dates/datetimes must be converted to ISO strings for JSON transport.
    rows: list[dict[str, Any]] = _dataframe_to_dicts(df)

    # Build column definitions from the schema.
    column_defs: list[ColumnDef] = []
    for col_name in df.columns:
        dtype = df.schema[col_name]
        grid_type = polars_dtype_to_grid_type(dtype)
        col_def = ColumnDef(
            field=col_name,
            header_name=_humanize_field_name(col_name),
            type=grid_type,
            flex=1,
        )
        column_defs.append(col_def)

    return rows, column_defs


def _dataframe_to_dicts(df: pl.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame to a list of JSON-safe dicts.

    Dates and datetimes are converted to ISO-8601 strings so they survive
    JSON serialisation.  Other types are left as-is (polars ``to_dicts()``
    already returns Python-native scalars for numeric / string / bool).
    """
    temporal_cols: set[str] = {
        name
        for name, dtype in df.schema.items()
        if isinstance(dtype, (pl.Date, pl.Datetime, pl.Time, pl.Duration))
    }

    if not temporal_cols:
        return df.to_dicts()

    # Build select expressions that preserve original column order,
    # casting temporal columns to String for JSON safety.
    exprs: list[pl.Expr] = [
        pl.col(c).cast(pl.String) if c in temporal_cols else pl.col(c)
        for c in df.columns
    ]
    return df.select(exprs).to_dicts()
