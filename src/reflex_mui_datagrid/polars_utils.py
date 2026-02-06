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


def _is_categorical_dtype(dtype: pl.DataType) -> bool:
    """Return True if the dtype is explicitly categorical (Categorical or Enum)."""
    return isinstance(dtype, (pl.Categorical, pl.Enum))


def _detect_single_select(
    df: pl.DataFrame,
    col_name: str,
    dtype: pl.DataType,
    max_unique_ratio: float,
    max_unique_abs: int,
) -> list[str] | None:
    """Decide whether *col_name* should be rendered as ``singleSelect``.

    Returns the sorted list of distinct values if the column qualifies,
    otherwise ``None``.

    A column qualifies when:
    * Its dtype is ``Categorical`` or ``Enum``, **or**
    * It is a string column whose number of distinct values is both
      <= *max_unique_abs* **and** <= *max_unique_ratio* * row_count.
    """
    if _is_categorical_dtype(dtype):
        values = df[col_name].cast(pl.String).unique().drop_nulls().sort().to_list()
        return values

    if not isinstance(dtype, pl.String):
        return None

    n_rows = df.height
    if n_rows == 0:
        return None

    unique_vals: list[str] = df[col_name].unique().drop_nulls().sort().to_list()
    n_unique = len(unique_vals)

    if n_unique <= max_unique_abs and n_unique / n_rows <= max_unique_ratio:
        return unique_vals

    return None


def lazyframe_to_datagrid(
    lf: pl.LazyFrame,
    *,
    id_field: str | None = None,
    limit: int | None = None,
    single_select_threshold: int = 20,
    single_select_ratio: float = 0.5,
) -> tuple[list[dict[str, Any]], list[ColumnDef]]:
    """Convert a polars LazyFrame into MUI DataGrid *rows* and *column_defs*.

    Args:
        lf: The polars LazyFrame to convert.
        id_field: Name of the column that serves as the unique row identifier.
            If ``None`` and no ``"id"`` column exists, a ``"__row_id__"``
            column is added automatically with a zero-based row index.
        limit: Optional maximum number of rows to collect.
        single_select_threshold: String columns with at most this many distinct
            values are automatically turned into ``singleSelect`` columns with
            a dropdown filter.  Set to ``0`` to disable auto-detection.
        single_select_ratio: Maximum ratio of unique values to row count for
            a string column to qualify as ``singleSelect`` (e.g. 0.5 means
            the column must have fewer than half as many unique values as
            rows).

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
        value_options: list[str] | None = None

        # Auto-detect singleSelect for categorical / low-cardinality columns.
        if single_select_threshold > 0:
            value_options = _detect_single_select(
                df, col_name, dtype,
                max_unique_ratio=single_select_ratio,
                max_unique_abs=single_select_threshold,
            )
        if value_options is not None:
            grid_type = "singleSelect"

        col_def = ColumnDef(
            field=col_name,
            header_name=_humanize_field_name(col_name),
            type=grid_type,
            flex=1,
            value_options=value_options,
        )
        column_defs.append(col_def)

    return rows, column_defs


def _dataframe_to_dicts(df: pl.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame to a list of JSON-safe dicts.

    Non-JSON-safe column types are converted automatically:
    * Temporal columns (Date, Datetime, Time, Duration) -> ISO-8601 strings.
    * List columns -> comma-joined strings (inner values cast to String first).
    * Struct columns -> cast to String.

    Other types are left as-is (polars ``to_dicts()`` already returns
    Python-native scalars for numeric / string / bool).
    """
    temporal_cols: set[str] = set()
    list_cols: set[str] = set()
    struct_cols: set[str] = set()

    for name, dtype in df.schema.items():
        if isinstance(dtype, (pl.Date, pl.Datetime, pl.Time, pl.Duration)):
            temporal_cols.add(name)
        elif isinstance(dtype, pl.List):
            list_cols.add(name)
        elif isinstance(dtype, pl.Struct):
            struct_cols.add(name)

    needs_cast = temporal_cols | list_cols | struct_cols
    if not needs_cast:
        return df.to_dicts()

    # Build select expressions that preserve original column order,
    # casting non-JSON-safe columns to String for safe serialisation.
    exprs: list[pl.Expr] = []
    for c in df.columns:
        if c in temporal_cols:
            exprs.append(pl.col(c).cast(pl.String))
        elif c in list_cols:
            exprs.append(pl.col(c).cast(pl.List(pl.String)).list.join(","))
        elif c in struct_cols:
            exprs.append(pl.col(c).cast(pl.String))
        else:
            exprs.append(pl.col(c))

    return df.select(exprs).to_dicts()
