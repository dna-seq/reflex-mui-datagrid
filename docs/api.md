# API Reference

## Components

### `data_grid(...)`

The main callable. Creates a `WrappedDataGrid` -- a DataGrid inside an auto-sized `<div>` container.

```python
from reflex_mui_datagrid import data_grid

data_grid(
    rows=State.rows,
    columns=State.columns,
    height="400px",
)
```

This is a `DataGridNamespace` instance that also exposes:
- `data_grid.column_def` -- the `ColumnDef` class
- `data_grid.root` -- `DataGrid.create` (without the auto-sizing wrapper)

#### Props

**Data:**

| Prop | Type | Description |
|------|------|-------------|
| `rows` | `list[dict[str, Any]]` | Row data. Each dict is one row. |
| `columns` | `list[dict[str, Any]]` | Column definitions. Use `ColumnDef(...).dict()` to generate. |

**Layout and container (handled by `WrappedDataGrid`):**

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `width` | `str` | `"100%"` | CSS width of the outer container div. |
| `height` | `str` | `"400px"` | CSS height of the outer container div. |
| `virtual_scroll` | `bool` | `False` | When `True`, sets `pageSize=100` and `pageSizeOptions=[25, 50, 100]` for smooth scrolling. |

**Display:**

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `loading` | `bool` | -- | Show loading overlay. |
| `density` | `str` | -- | `"comfortable"`, `"compact"`, or `"standard"`. |
| `row_height` | `int` | -- | Row height in pixels. |
| `column_header_height` | `int` | -- | Header height in pixels. |
| `show_toolbar` | `bool` | -- | Show the built-in MUI toolbar (columns, filters, export, search). |
| `row_id_field` | `str` | -- | Field name to use as row ID. Generates a JS `getRowId` callback. |

**Selection:**

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `checkbox_selection` | `bool` | -- | Show checkbox column for row selection. |
| `row_selection` | `bool` | -- | Enable row selection. |
| `disable_row_selection_on_click` | `bool` | -- | Prevent row selection when clicking a row. |

**Pagination:**

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `pagination_model` | `dict[str, int]` | -- | `{"page": 0, "pageSize": 10}` -- controlled pagination. |
| `page_size_options` | `list[int]` | -- | Available page sizes, e.g. `[5, 10, 25]`. |
| `auto_page_size` | `bool` | -- | Automatically set page size to fill the container. |
| `hide_footer_pagination` | `bool` | -- | Hide the pagination footer. |

**Sorting:**

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `sort_model` | `list[dict]` | -- | Controlled sort state: `[{"field": "name", "sort": "asc"}]`. |
| `sorting_order` | `list` | -- | Allowed sort directions, e.g. `["asc", "desc", None]`. |

**Filtering:**

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `disable_column_filter` | `bool` | -- | Disable column filtering entirely. |
| `filter_debounce_ms` | `int` | -- | Debounce delay for filter input in milliseconds. |

**Column features:**

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `column_visibility_model` | `dict[str, bool]` | -- | `{"salary": False}` hides the salary column. |
| `column_grouping_model` | `list[dict[str, Any]]` | -- | Define multi-level headers, e.g. `[{"groupId": "Personal", "children": [{"field": "firstName"}]}]`. |
| `disable_column_selector` | `bool` | -- | Disable the column visibility panel. |
| `disable_density_selector` | `bool` | -- | Disable the density selector. |

#### Event Handlers

All event handlers strip non-serializable keys (api, column, node, DOM event) before passing data to Python.

| Event | Callback Signature | Description |
|-------|-------------------|-------------|
| `on_row_click` | `(params: dict) -> None` | Row clicked. `params` contains `id`, `row`, `field`, etc. |
| `on_cell_click` | `(params: dict) -> None` | Cell clicked. `params` contains `id`, `field`, `value`, `row`, etc. |
| `on_sort_model_change` | `(model: list[dict]) -> None` | Sort changed. `model` is `[{"field": "name", "sort": "asc"}]`. |
| `on_filter_model_change` | `(model: dict) -> None` | Filter changed. `model` contains `items`, `logicOperator`, etc. |
| `on_pagination_model_change` | `(model: dict) -> None` | Page changed. `model` is `{"page": 0, "pageSize": 10}`. |
| `on_row_selection_model_change` | `(model: dict) -> None` | Selection changed. `model` is `{"type": "include", "ids": [...]}`. |
| `on_column_visibility_model_change` | `(model: dict) -> None` | Column visibility changed. `model` is `{"column_name": bool}`. |

---

## Models

### `ColumnDef`

Column definition model. Inherits from `PropsBase` -- all attributes are auto-converted from snake_case to camelCase when serialized with `.dict()`.

```python
from reflex_mui_datagrid import ColumnDef

col = ColumnDef(
    field="salary",
    header_name="Annual Salary",
    type="number",
    flex=1,
    filterable=True,
    sortable=True,
)
# col.dict() -> {"field": "salary", "headerName": "Annual Salary", "type": "number", "flex": 1, ...}
```

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `field` | `str` | *required* | Column identifier, must match a key in the row dicts. |
| `header_name` | `str \| None` | `None` | Display name in the column header. |
| `width` | `int \| None` | `None` | Fixed width in pixels. |
| `min_width` | `int \| None` | `None` | Minimum width in pixels. |
| `max_width` | `int \| None` | `None` | Maximum width in pixels. |
| `flex` | `int \| None` | `None` | Flex grow factor (takes remaining space). |
| `type` | `str \| None` | `None` | `"string"`, `"number"`, `"date"`, `"dateTime"`, `"boolean"`, or `"singleSelect"`. |
| `align` | `str \| None` | `None` | Cell alignment: `"left"`, `"center"`, or `"right"`. |
| `header_align` | `str \| None` | `None` | Header alignment: `"left"`, `"center"`, or `"right"`. |
| `editable` | `bool` | `False` | Allow cell editing. |
| `sortable` | `bool` | `True` | Allow sorting on this column. |
| `filterable` | `bool` | `True` | Allow filtering on this column. |
| `resizable` | `bool` | `True` | Allow column resizing. |
| `hide` | `bool` | `False` | Hide this column. |
| `description` | `str \| None` | `None` | Tooltip shown when hovering the column header. |
| `value_options` | `list[str] \| None` | `None` | Dropdown options for `singleSelect` columns. |
| `value_getter` | `rx.Var \| None` | `None` | JS expression for computed column values. |
| `value_formatter` | `rx.Var \| None` | `None` | JS expression to format cell display values. |
| `cell_class_name` | `str \| None` | `None` | CSS class name for cells in this column. |
| `render_cell` | `rx.Var \| None` | `None` | Custom JS cell renderer. |
| `disable_column_menu` | `bool` | `False` | Disable the column menu (three-dot icon). |

---

## Polars Utilities

### `lazyframe_to_datagrid(lf, *, id_field=None, show_id_field=False, limit=None, single_select_threshold=20, single_select_ratio=0.5)`

Convert a polars `LazyFrame` to DataGrid-ready `(rows, column_defs)`.

```python
from reflex_mui_datagrid import lazyframe_to_datagrid

rows, col_defs = lazyframe_to_datagrid(lf)
# rows: list[dict[str, Any]]       -- ready for the `rows` prop
# col_defs: list[ColumnDef]        -- call c.dict() for the `columns` prop
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `lf` | `pl.LazyFrame` | *required* | The LazyFrame to convert. |
| `id_field` | `str \| None` | `None` | Column to use as row ID. If `None` and no `"id"` column exists, a `__row_id__` column is auto-generated. |
| `show_id_field` | `bool` | `False` | Whether to include the row identifier as a visible column in the grid. |
| `limit` | `int \| None` | `None` | Max rows to collect (uses `.head(limit)`). |
| `single_select_threshold` | `int` | `20` | String columns with at most this many unique values become `singleSelect`. Set to `0` to disable. |
| `single_select_ratio` | `float` | `0.5` | Max ratio of unique values to total rows for `singleSelect` detection. |

**Automatic behavior:**

- **Row ID**: If no `id` column and no `id_field` specified, a `__row_id__` column with zero-based index is added. The ID column is hidden from the visible grid by default.
- **Column types**: Polars dtypes are mapped to DataGrid types:
  - `Int*/UInt*/Float*/Decimal` -> `"number"`
  - `Boolean` -> `"boolean"`
  - `Date` -> `"date"`
  - `Datetime` -> `"dateTime"`
  - `Categorical`/`Enum` -> `"singleSelect"` (always, with distinct values as options)
  - `String` -> `"singleSelect"` if low-cardinality, else `"string"`
  - Everything else -> `"string"`
- **JSON safety**: Temporal columns become ISO strings, `List` columns become comma-joined strings, `Struct` columns become strings.
- **Header names**: snake_case field names are humanized (`first_name` -> `"First Name"`).

### `show_dataframe(data, **kwargs)`

One-liner to turn a polars DataFrame or LazyFrame into a DataGrid component. Calls `lazyframe_to_datagrid` internally and returns a ready-to-render `data_grid(...)` component.

```python
import polars as pl
from reflex_mui_datagrid import show_dataframe

df = pl.read_csv("my_data.csv")
grid = show_dataframe(df, height="500px", density="compact")
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data` | `pl.LazyFrame \| pl.DataFrame` | *required* | The polars data to visualize. |
| `id_field` | `str \| None` | `None` | Column to use as row ID. |
| `show_id_field` | `bool` | `False` | Whether to show the ID column. |
| `limit` | `int \| None` | `None` | Max rows to collect. |
| `single_select_threshold` | `int` | `20` | Max distinct values for auto `singleSelect`. |
| `single_select_ratio` | `float` | `0.5` | Max unique/row ratio for `singleSelect`. |
| `column_descriptions` | `dict[str, str] \| None` | `None` | `{column: description}` for tooltips. |
| `show_toolbar` | `bool` | `True` | Show MUI toolbar. |
| `show_description_in_header` | `bool` | `False` | Show descriptions as subtitles. |
| `density` | `str \| None` | `None` | `"comfortable"`, `"compact"`, or `"standard"`. |
| `height` | `str` | `"600px"` | CSS height of the grid container. |
| `width` | `str` | `"100%"` | CSS width of the grid container. |
| `column_header_height` | `int \| None` | `None` | Header height in px. |
| `checkbox_selection` | `bool` | `False` | Show checkbox column. |
| `on_row_click` | `rx.EventHandler \| None` | `None` | Row click handler. |

**Best for:** prototyping, static dashboards, exploration. For reactive grids, use `lazyframe_to_datagrid` inside `rx.State`.

### `polars_dtype_to_grid_type(dtype)`

Map a single polars `DataType` to a DataGrid column type string.

```python
from reflex_mui_datagrid import polars_dtype_to_grid_type
import polars as pl

polars_dtype_to_grid_type(pl.Int64)    # "number"
polars_dtype_to_grid_type(pl.Boolean)  # "boolean"
polars_dtype_to_grid_type(pl.Date)     # "date"
polars_dtype_to_grid_type(pl.String)   # "string"
```

---

## Architecture

The library is structured as:

```
src/reflex_mui_datagrid/
    __init__.py          # Public exports
    datagrid.py          # DataGrid, WrappedDataGrid, DataGridNamespace
    models.py            # ColumnDef (PropsBase)
    polars_utils.py      # lazyframe_to_datagrid, show_dataframe, polars_dtype_to_grid_type
    polars_bio_utils.py  # bio_lazyframe_to_datagrid, extract_vcf_descriptions (optional [bio] extra)
    UnlimitedDataGrid.js # JS patch removing MUI's 100-row page-size cap
```

### Component hierarchy

- **`DataGrid(rx.Component)`** -- core wrapper for `@mui/x-data-grid`. Requires a parent container with explicit dimensions.
- **`WrappedDataGrid(DataGrid)`** -- wraps `DataGrid` in a `<div>` with `width`/`height`. Supports `virtual_scroll` parameter.
- **`DataGridNamespace(rx.ComponentNamespace)`** -- provides `data_grid(...)` callable and `data_grid.column_def`.

### npm dependencies

Installed automatically by Reflex:
- `@mui/x-data-grid@^8.27.0`
- `@mui/material@^7.0.0`
- `@emotion/react@^11.14.0`
- `@emotion/styled@^11.14.0`

### MUI DataGrid Community limitations

The Community (MIT) edition normally has a hard limit of **100 rows per page**. This library removes that limit via `UnlimitedDataGrid.js`, which patches the page-size cap and allows `pagination=False`. With pagination off (the default), all rows are scrollable and MUI's built-in row virtualisation keeps performance smooth.
