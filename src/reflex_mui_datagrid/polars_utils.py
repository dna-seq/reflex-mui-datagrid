"""Utilities for converting polars LazyFrames to MUI X DataGrid rows and columns."""

from typing import Any, Literal

import polars as pl
import reflex as rx

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


def _col_to_str_expr(col: pl.Expr, dtype: pl.DataType) -> pl.Expr:
    """Convert a column expression to a String, handling List/Struct types.

    * ``List(T)`` → cast inner to String, then ``list.join(",")``
    * ``Array(T, n)`` → cast to ``List(String)``, then ``list.join(",")``
    * ``Struct`` → ``cast(pl.String)`` (Polars supports this natively)
    * Everything else → ``cast(pl.String)``
    """
    if isinstance(dtype, pl.List):
        return col.cast(pl.List(pl.String)).list.join(",")
    if isinstance(dtype, pl.Array):
        return col.cast(pl.List(pl.String)).list.join(",")
    if isinstance(dtype, pl.Struct):
        return col.cast(pl.String)
    return col.cast(pl.String)


def _col_to_str_code(col_code: str, dtype: pl.DataType) -> str:
    """Return a code snippet that converts a column to String.

    Mirrors :func:`_col_to_str_expr` but produces a Python code string
    for :func:`_filter_item_to_code`.
    """
    if isinstance(dtype, pl.List):
        return f'{col_code}.cast(pl.List(pl.String)).list.join(",")'
    if isinstance(dtype, pl.Array):
        return f'{col_code}.cast(pl.List(pl.String)).list.join(",")'
    if isinstance(dtype, pl.Struct):
        return f'{col_code}.cast(pl.String)'
    return f'{col_code}.cast(pl.String)'


def _detect_single_select(
    df: pl.DataFrame,
    col_name: str,
    dtype: pl.DataType,
    max_unique_abs: int,
) -> list[str] | None:
    """Decide whether *col_name* should be rendered as ``singleSelect``.

    Returns the sorted list of distinct values if the column qualifies,
    otherwise ``None``.

    A column qualifies when:
    * Its dtype is ``Categorical`` or ``Enum``, **or**
    * It is a string column whose number of distinct values is
      <= *max_unique_abs*.

    MUI DataGrid renders ``singleSelect`` as a scrollable/searchable
    dropdown, so several hundred values are perfectly usable.  Only
    truly high-cardinality columns (free-form text, sequences, etc.)
    should fall back to the text filter operators.
    """
    if _is_categorical_dtype(dtype):
        values = df[col_name].cast(pl.String).unique().drop_nulls().sort().to_list()
        return values

    if not isinstance(dtype, pl.String):
        return None

    if df.height == 0:
        return None

    unique_vals: list[str] = df[col_name].unique().drop_nulls().sort().to_list()
    if len(unique_vals) <= max_unique_abs:
        return unique_vals

    return None


def lazyframe_to_datagrid(
    lf: pl.LazyFrame,
    *,
    id_field: str | None = None,
    show_id_field: bool = False,
    limit: int | None = None,
    single_select_threshold: int = 500,
    column_descriptions: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[ColumnDef]]:
    """Convert a polars LazyFrame into MUI DataGrid *rows* and *column_defs*.

    Args:
        lf: The polars LazyFrame to convert.
        id_field: Name of the column that serves as the unique row identifier.
            If ``None`` and no ``"id"`` column exists, a ``"__row_id__"``
            column is added automatically with a zero-based row index.
        show_id_field: Whether to include the row identifier as a visible column.
        limit: Optional maximum number of rows to collect.
        single_select_threshold: String columns with at most this many distinct
            values are automatically turned into ``singleSelect`` columns with
            a dropdown filter.  Set to ``0`` to disable auto-detection.
            MUI renders dropdowns as scrollable/searchable lists, so several
            hundred values are perfectly usable.
        column_descriptions: Optional mapping of column names to human-readable
            descriptions.  When provided, each matching column definition gets
            its ``description`` field set, which MUI DataGrid renders as a
            tooltip on the column header.  To show descriptions as subtitles
            in the header (not just tooltips), pass
            ``show_description_in_header=True`` to the ``data_grid()``
            component.

    Returns:
        A ``(rows, column_defs)`` tuple where *rows* is a list of dicts
        ready for the DataGrid ``rows`` prop, and *column_defs* is a list of
        :class:`ColumnDef` instances inferred from the schema.
    """
    if limit is not None:
        lf = lf.head(limit)

    df = lf.collect()

    # Ensure every row has an id MUI DataGrid can use.
    # If the caller specified an id_field, trust it.  Otherwise check
    # whether the DataFrame has an "id" column with *unique* values.
    # VCF files, for example, have an "id" column that is almost always
    # empty/missing ("."), so blindly using it would give every row the
    # same key and MUI would render duplicates.
    effective_id_field = id_field
    if effective_id_field is None:
        if "id" in df.columns and df["id"].n_unique() == df.height:
            effective_id_field = "id"
        else:
            df = df.with_row_index("__row_id__")
            effective_id_field = "__row_id__"

    # Build rows – serialise to Python dicts.
    # Dates/datetimes must be converted to ISO strings for JSON transport.
    rows: list[dict[str, Any]] = _dataframe_to_dicts(df)

    # Build column definitions from the schema.
    column_defs: list[ColumnDef] = []
    for col_name in df.columns:
        # Hide the ID field by default.
        if not show_id_field and col_name == effective_id_field:
            continue

        dtype = df.schema[col_name]
        grid_type = polars_dtype_to_grid_type(dtype)
        value_options: list[str] | None = None

        # Auto-detect singleSelect for categorical / low-cardinality columns.
        if single_select_threshold > 0:
            value_options = _detect_single_select(
                df, col_name, dtype,
                max_unique_abs=single_select_threshold,
            )
        if value_options is not None:
            grid_type = "singleSelect"

        description: str | None = None
        if column_descriptions is not None:
            description = column_descriptions.get(col_name)

        col_def = ColumnDef(
            field=col_name,
            header_name=_humanize_field_name(col_name),
            type=grid_type,
            value_options=value_options,
            description=description,
        )
        column_defs.append(col_def)

    return rows, column_defs


def build_column_defs_from_schema(
    schema: pl.Schema,
    *,
    value_options_map: dict[str, list[str]] | None = None,
    column_descriptions: dict[str, str] | None = None,
    id_field: str | None = None,
    show_id_field: bool = False,
) -> list[ColumnDef]:
    """Build a list of :class:`ColumnDef` from a polars Schema without collecting data.

    This is the server-side counterpart of the column-building logic in
    :func:`lazyframe_to_datagrid`.  It works purely from the schema (no
    ``collect()`` needed), which makes it suitable for very large LazyFrames
    where you don't want to materialise the full dataset just to infer
    column definitions.

    Args:
        schema: A polars ``Schema`` (e.g. ``lf.collect_schema()``).
        value_options_map: Pre-computed mapping of column names to their
            allowed values.  Columns present in this mapping are rendered
            as ``singleSelect`` with a dropdown filter.  For example::

                {"chrom": ["1", "2", ..., "X", "Y"]}

        column_descriptions: Optional ``{column: description}`` mapping
            for column header tooltips / subtitles.
        id_field: Name of the column used as the unique row identifier.
            When *show_id_field* is ``False`` (the default), this column
            is excluded from the returned column definitions.
        show_id_field: Whether to include the *id_field* column in the
            result.

    Returns:
        A list of :class:`ColumnDef` instances inferred from *schema*.
    """
    if value_options_map is None:
        value_options_map = {}

    column_defs: list[ColumnDef] = []
    for col_name, dtype in schema.items():
        # Hide the ID field by default.
        if not show_id_field and col_name == id_field:
            continue

        grid_type = polars_dtype_to_grid_type(dtype)
        value_options: list[str] | None = None

        # Use pre-computed value options if provided.
        if col_name in value_options_map:
            value_options = value_options_map[col_name]
            grid_type = "singleSelect"
        elif _is_categorical_dtype(dtype):
            # Categorical / Enum columns are singleSelect even without
            # pre-computed options (the grid will show a dropdown but the
            # caller should ideally provide the options via the map).
            grid_type = "singleSelect"

        description: str | None = None
        if column_descriptions is not None:
            description = column_descriptions.get(col_name)

        col_def = ColumnDef(
            field=col_name,
            header_name=_humanize_field_name(col_name),
            type=grid_type,
            value_options=value_options,
            description=description,
        )
        column_defs.append(col_def)

    return column_defs


# ---------------------------------------------------------------------------
# Server-side filtering
# ---------------------------------------------------------------------------

def _build_filter_expr(
    item: dict[str, Any],
    schema: pl.Schema,
) -> pl.Expr | None:
    """Translate a single MUI DataGrid filter item to a Polars expression.

    Args:
        item: A filter item dict, e.g.
            ``{"field": "age", "operator": ">", "value": 30}``.
        schema: The LazyFrame schema, used to determine column types.

    Returns:
        A polars expression, or ``None`` if the item cannot be translated
        (e.g. unknown operator or missing field).
    """
    field: str | None = item.get("field")
    operator: str | None = item.get("operator")
    value: Any = item.get("value")

    if field is None or operator is None:
        return None
    if field not in schema:
        return None

    col = pl.col(field)
    dtype = schema[field]
    grid_type = polars_dtype_to_grid_type(dtype)
    str_col = _col_to_str_expr(col, dtype)

    # -- operators that don't need a value --
    if operator == "isEmpty":
        return col.is_null() | (str_col == "")
    if operator == "isNotEmpty":
        return col.is_not_null() & (str_col != "")

    # Remaining operators require a value.
    if value is None:
        return None

    # -- singleSelect operators --
    if operator == "is":
        return str_col == str(value)
    if operator == "not":
        return str_col != str(value)
    if operator == "isAnyOf":
        if not isinstance(value, list):
            return None
        return str_col.is_in([str(v) for v in value])

    # -- string operators --
    if grid_type == "string" or _is_categorical_dtype(dtype):
        str_value = str(value)
        if operator == "contains":
            return str_col.str.contains(str_value, literal=True)
        if operator == "equals":
            return str_col == str_value
        if operator == "startsWith":
            return str_col.str.starts_with(str_value)
        if operator == "endsWith":
            return str_col.str.ends_with(str_value)
        return None

    # -- numeric operators --
    if grid_type == "number":
        num_value = _coerce_numeric(value)
        if num_value is None:
            return None
        if operator in ("=", "equals"):
            return col == num_value
        if operator in ("!=", "not"):
            return col != num_value
        if operator == ">":
            return col > num_value
        if operator == ">=":
            return col >= num_value
        if operator == "<":
            return col < num_value
        if operator == "<=":
            return col <= num_value
        return None

    return None


def _coerce_numeric(value: Any) -> int | float | None:
    """Try to coerce *value* to a number."""
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        # Try int first, then float
        for conv in (int, float):
            try:  # noqa: SIM105  — intentional minimal try for numeric coercion
                return conv(value)
            except ValueError:
                continue
    return None


def apply_filter_model(
    lf: pl.LazyFrame,
    filter_model: dict[str, Any],
    schema: pl.Schema | None = None,
) -> pl.LazyFrame:
    """Apply a MUI DataGrid filter model to a Polars LazyFrame.

    Translates the MUI ``filterModel`` JSON structure into Polars
    expressions and returns the filtered LazyFrame — **no collect**.

    The filter model has the shape::

        {
            "items": [
                {"field": "name", "operator": "contains", "value": "foo"},
                {"field": "age",  "operator": ">",        "value": 30},
            ],
            "logicOperator": "and"   # or "or"
        }

    Supported MUI operators:

    * **String**: ``contains``, ``equals``, ``startsWith``, ``endsWith``,
      ``isEmpty``, ``isNotEmpty``, ``isAnyOf``
    * **Number**: ``=``, ``!=``, ``>``, ``>=``, ``<``, ``<=``,
      ``isEmpty``, ``isNotEmpty``
    * **singleSelect**: ``is``, ``not``, ``isAnyOf``

    Args:
        lf: The polars LazyFrame to filter.
        filter_model: MUI DataGrid filter model dict.
        schema: Optional schema override.  If ``None``, the schema is
            obtained from ``lf.collect_schema()``.

    Returns:
        The filtered ``pl.LazyFrame``.
    """
    items: list[dict[str, Any]] = filter_model.get("items", [])
    if not items:
        return lf

    if schema is None:
        schema = lf.collect_schema()

    logic: str = filter_model.get("logicOperator", "and").lower()

    exprs: list[pl.Expr] = []
    for item in items:
        expr = _build_filter_expr(item, schema)
        if expr is not None:
            exprs.append(expr)

    if not exprs:
        return lf

    if logic == "or":
        combined = exprs[0]
        for e in exprs[1:]:
            combined = combined | e
    else:
        combined = exprs[0]
        for e in exprs[1:]:
            combined = combined & e

    return lf.filter(combined)


# ---------------------------------------------------------------------------
# Server-side sorting
# ---------------------------------------------------------------------------

def apply_sort_model(
    lf: pl.LazyFrame,
    sort_model: list[dict[str, str]],
) -> pl.LazyFrame:
    """Apply a MUI DataGrid sort model to a Polars LazyFrame.

    Translates the MUI ``sortModel`` array into a ``lf.sort()`` call and
    returns the sorted LazyFrame — **no collect**.

    The sort model has the shape::

        [
            {"field": "chrom", "sort": "asc"},
            {"field": "pos",   "sort": "desc"},
        ]

    Args:
        lf: The polars LazyFrame to sort.
        sort_model: MUI DataGrid sort model list.

    Returns:
        The sorted ``pl.LazyFrame``.
    """
    if not sort_model:
        return lf

    by: list[str] = []
    descending: list[bool] = []

    for entry in sort_model:
        field = entry.get("field")
        direction = entry.get("sort", "asc")
        if field is None:
            continue
        by.append(field)
        descending.append(direction == "desc")

    if not by:
        return lf

    return lf.sort(by=by, descending=descending)


# ---------------------------------------------------------------------------
# Polars code generation from MUI filter/sort models
# ---------------------------------------------------------------------------

def _filter_item_to_code(
    item: dict[str, Any],
    schema: pl.Schema,
) -> str | None:
    """Translate a single MUI filter item to a Polars code snippet string."""
    field: str | None = item.get("field")
    operator: str | None = item.get("operator")
    value: Any = item.get("value")

    if field is None or operator is None:
        return None
    if field not in schema:
        return None

    col = f'pl.col("{field}")'
    dtype = schema[field]
    grid_type = polars_dtype_to_grid_type(dtype)
    str_col = _col_to_str_code(col, dtype)

    # Operators that don't need a value
    if operator == "isEmpty":
        return f'({col}.is_null() | ({str_col} == ""))'
    if operator == "isNotEmpty":
        return f'({col}.is_not_null() & ({str_col} != ""))'

    if value is None:
        return None

    # singleSelect operators
    if operator == "is":
        return f'{str_col} == "{value}"'
    if operator == "not":
        return f'{str_col} != "{value}"'
    if operator == "isAnyOf":
        if not isinstance(value, list):
            return None
        vals_repr = repr([str(v) for v in value])
        return f"{str_col}.is_in({vals_repr})"

    # String operators
    if grid_type == "string" or _is_categorical_dtype(dtype):
        escaped = str(value).replace('"', '\\"')
        if operator == "contains":
            return f'{str_col}.str.contains("{escaped}", literal=True)'
        if operator == "equals":
            return f'{str_col} == "{escaped}"'
        if operator == "startsWith":
            return f'{str_col}.str.starts_with("{escaped}")'
        if operator == "endsWith":
            return f'{str_col}.str.ends_with("{escaped}")'
        return None

    # Numeric operators
    if grid_type == "number":
        num_value = _coerce_numeric(value)
        if num_value is None:
            return None
        if operator in ("=", "equals"):
            return f"{col} == {num_value}"
        if operator in ("!=", "not"):
            return f"{col} != {num_value}"
        if operator in (">", ">=", "<", "<="):
            return f"{col} {operator} {num_value}"
        return None

    return None


def generate_polars_code(
    filter_model: dict[str, Any] | None = None,
    sort_model: list[dict[str, Any]] | None = None,
    schema: pl.Schema | None = None,
) -> str:
    """Generate readable Polars Python code from MUI filter/sort models.

    Returns a multi-line string that can be copy-pasted into a script.
    The code assumes a variable ``lf`` (LazyFrame) already exists.

    Args:
        filter_model: MUI DataGrid filter model dict (may be ``None``
            or empty).
        sort_model: MUI DataGrid sort model list (may be ``None`` or
            empty).
        schema: The LazyFrame schema, used to determine column types
            for generating correct filter expressions.

    Returns:
        A string of valid Python code, or an empty string if there are
        no active filters or sorts.
    """
    lines: list[str] = []
    lines.append("import polars as pl")
    lines.append("")
    lines.append("# Apply the filters and sorts you selected in the grid:")

    has_filter = False
    if filter_model and filter_model.get("items") and schema is not None:
        items = filter_model["items"]
        logic: str = filter_model.get("logicOperator", "and").lower()
        code_parts: list[str] = []
        for item in items:
            code = _filter_item_to_code(item, schema)
            if code is not None:
                code_parts.append(code)

        if code_parts:
            has_filter = True
            if len(code_parts) == 1:
                lines.append(f"lf = lf.filter({code_parts[0]})")
            else:
                joiner = " | " if logic == "or" else " & "
                combined = joiner.join(f"({p})" for p in code_parts)
                lines.append(f"lf = lf.filter({combined})")

    has_sort = False
    if sort_model:
        by_fields: list[str] = []
        descending_flags: list[bool] = []
        for entry in sort_model:
            field = entry.get("field")
            direction = entry.get("sort", "asc")
            if field is None:
                continue
            by_fields.append(field)
            descending_flags.append(direction == "desc")

        if by_fields:
            has_sort = True
            if len(by_fields) == 1:
                desc_str = "True" if descending_flags[0] else "False"
                lines.append(
                    f'lf = lf.sort("{by_fields[0]}", descending={desc_str})'
                )
            else:
                by_repr = repr(by_fields)
                desc_repr = repr(descending_flags)
                lines.append(
                    f"lf = lf.sort(by={by_repr}, descending={desc_repr})"
                )

    if not has_filter and not has_sort:
        return ""

    lines.append("")
    lines.append("# Collect the result:")
    lines.append("df = lf.collect()")
    return "\n".join(lines)


def generate_sql_where(
    filter_model: dict[str, Any] | None = None,
    sort_model: list[dict[str, Any]] | None = None,
    schema: pl.Schema | None = None,
    *,
    table_name: str = "df",
) -> str:
    """Generate a SQL WHERE clause from MUI filter/sort models.

    Returns a SQL string that can be copy-pasted into DuckDB, Postgres,
    SQLite, or any SQL-compatible tool.  The SQL assumes a table or view
    named *table_name* already exists.

    Args:
        filter_model: MUI DataGrid filter model dict (may be ``None``
            or empty).
        sort_model: MUI DataGrid sort model list (may be ``None`` or
            empty).
        schema: The LazyFrame schema, used to determine column types
            for generating correct filter expressions.
        table_name: Name of the SQL table/view.  Defaults to ``"df"``.

    Returns:
        A string of valid SQL, or an empty string if there are no
        active filters or sorts.
    """
    parts: list[str] = []
    parts.append(f"SELECT * FROM {table_name}")

    has_filter = False
    if filter_model and filter_model.get("items") and schema is not None:
        items = filter_model["items"]
        logic: str = filter_model.get("logicOperator", "and").upper()
        sql_conditions: list[str] = []
        for item in items:
            sql = _filter_item_to_sql(item, schema)
            if sql is not None:
                sql_conditions.append(sql)

        if sql_conditions:
            has_filter = True
            joiner = f" {logic} "
            where_clause = joiner.join(sql_conditions)
            parts.append(f"WHERE {where_clause}")

    has_sort = False
    if sort_model:
        order_parts: list[str] = []
        for entry in sort_model:
            field = entry.get("field")
            direction = entry.get("sort", "asc").upper()
            if field is None:
                continue
            order_parts.append(f'"{field}" {direction}')

        if order_parts:
            has_sort = True
            parts.append(f"ORDER BY {', '.join(order_parts)}")

    if not has_filter and not has_sort:
        return ""

    return "\n".join(parts) + ";"


def _filter_item_to_sql(
    item: dict[str, Any],
    schema: pl.Schema,
) -> str | None:
    """Translate a single MUI filter item to a SQL condition string."""
    field: str | None = item.get("field")
    operator: str | None = item.get("operator")
    value: Any = item.get("value")

    if field is None or operator is None:
        return None
    if field not in schema:
        return None

    col = f'"{field}"'
    dtype = schema[field]
    grid_type = polars_dtype_to_grid_type(dtype)

    # Operators that don't need a value
    if operator == "isEmpty":
        return f"({col} IS NULL OR CAST({col} AS TEXT) = '')"
    if operator == "isNotEmpty":
        return f"({col} IS NOT NULL AND CAST({col} AS TEXT) != '')"

    if value is None:
        return None

    # singleSelect operators
    if operator == "is":
        escaped = str(value).replace("'", "''")
        return f"CAST({col} AS TEXT) = '{escaped}'"
    if operator == "not":
        escaped = str(value).replace("'", "''")
        return f"CAST({col} AS TEXT) != '{escaped}'"
    if operator == "isAnyOf":
        if not isinstance(value, list):
            return None
        vals = ", ".join(f"'{str(v).replace(chr(39), chr(39)*2)}'" for v in value)
        return f"CAST({col} AS TEXT) IN ({vals})"

    # String operators
    if grid_type == "string" or _is_categorical_dtype(dtype):
        escaped = str(value).replace("'", "''")
        if operator == "contains":
            return f"CAST({col} AS TEXT) LIKE '%{escaped}%'"
        if operator == "equals":
            return f"CAST({col} AS TEXT) = '{escaped}'"
        if operator == "startsWith":
            return f"CAST({col} AS TEXT) LIKE '{escaped}%'"
        if operator == "endsWith":
            return f"CAST({col} AS TEXT) LIKE '%{escaped}'"
        return None

    # Numeric operators
    if grid_type == "number":
        num_value = _coerce_numeric(value)
        if num_value is None:
            return None
        if operator in ("=", "equals"):
            return f"{col} = {num_value}"
        if operator in ("!=", "not"):
            return f"{col} != {num_value}"
        if operator in (">", ">=", "<", "<="):
            return f"{col} {operator} {num_value}"
        return None

    return None


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


# ---------------------------------------------------------------------------
# Quick-visualisation helper
# ---------------------------------------------------------------------------

def show_dataframe(
    data: pl.LazyFrame | pl.DataFrame,
    *,
    id_field: str | None = None,
    show_id_field: bool = False,
    limit: int | None = None,
    single_select_threshold: int = 500,
    column_descriptions: dict[str, str] | None = None,
    show_toolbar: bool = True,
    show_description_in_header: bool = False,
    density: Literal["comfortable", "compact", "standard"] | None = None,
    height: str = "600px",
    width: str = "100%",
    column_header_height: int | None = None,
    checkbox_selection: bool = False,
    on_row_click: rx.EventHandler | None = None,
) -> rx.Component:
    """One-liner to turn a polars DataFrame or LazyFrame into a DataGrid component.

    This is a convenience wrapper that calls :func:`lazyframe_to_datagrid`
    internally and returns a ready-to-render ``data_grid(...)`` component.
    It is designed for the common case where you just want to visualise a
    DataFrame quickly without manually wiring up rows/columns/state.

    Because the data is materialised at component-build time (not inside
    a State event handler), this helper is best suited for:

    * Prototyping and exploration
    * Static or slowly-changing datasets
    * Dashboards that load data once at startup

    For fully reactive grids (data changes in response to user actions),
    use :func:`lazyframe_to_datagrid` inside a ``rx.State`` event handler
    and pass the rows/columns as state vars.

    Args:
        data: A polars ``LazyFrame`` or ``DataFrame`` to visualise.
        id_field: Column to use as the unique row identifier.
        show_id_field: Whether to show the ID column in the grid.
        limit: Maximum number of rows to collect.
        single_select_threshold: Max distinct values for auto ``singleSelect``.
        column_descriptions: Optional ``{column: description}`` mapping.
        show_toolbar: Show the MUI toolbar (columns, filters, density, export).
        show_description_in_header: Show column descriptions as subtitles.
        density: Grid density (``"comfortable"``, ``"compact"``, ``"standard"``).
        height: CSS height of the grid container.
        width: CSS width of the grid container.
        column_header_height: Header height in pixels (useful when
            ``show_description_in_header=True``).
        checkbox_selection: Show checkbox column for row selection.
        on_row_click: Optional event handler for row clicks.

    Returns:
        A ``data_grid(...)`` Reflex component ready to be placed in a page.

    Example::

        import polars as pl
        from reflex_mui_datagrid import show_dataframe

        df = pl.read_csv("my_data.csv")
        # In your page function:
        def index() -> rx.Component:
            return show_dataframe(df, height="500px", show_toolbar=True)
    """
    from reflex_mui_datagrid.datagrid import data_grid

    lf = data.lazy() if isinstance(data, pl.DataFrame) else data

    rows, col_defs = lazyframe_to_datagrid(
        lf,
        id_field=id_field,
        show_id_field=show_id_field,
        limit=limit,
        single_select_threshold=single_select_threshold,
        column_descriptions=column_descriptions,
    )

    # Determine the effective row-id field for the grid.
    row_id_field: str | None = id_field
    if row_id_field is None:
        # Check if __row_id__ was auto-generated (it would be in the rows).
        if rows and "__row_id__" in rows[0]:
            row_id_field = "__row_id__"

    grid_kwargs: dict[str, Any] = {
        "rows": rows,
        "columns": [c.dict() for c in col_defs],
        "show_toolbar": show_toolbar,
        "height": height,
        "width": width,
        "checkbox_selection": checkbox_selection,
    }
    if row_id_field is not None:
        grid_kwargs["row_id_field"] = row_id_field
    if show_description_in_header:
        grid_kwargs["show_description_in_header"] = True
    if density is not None:
        grid_kwargs["density"] = density
    if column_header_height is not None:
        grid_kwargs["column_header_height"] = column_header_height
    if on_row_click is not None:
        grid_kwargs["on_row_click"] = on_row_click

    return data_grid(**grid_kwargs)
