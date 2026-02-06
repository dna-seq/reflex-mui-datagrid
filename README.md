# reflex-mui-datagrid

Reflex wrapper for the [MUI X DataGrid](https://mui.com/x/react-data-grid/) (v8) React component, with built-in [polars](https://pola.rs/) LazyFrame support.

## Installation

```bash
uv add reflex-mui-datagrid
```

## Quick Start

```python
import polars as pl
import reflex as rx
from reflex_mui_datagrid import data_grid, lazyframe_to_datagrid

class State(rx.State):
    rows: list[dict] = []
    columns: list[dict] = []

    def load_data(self) -> None:
        lf = pl.LazyFrame({
            "id": [1, 2, 3],
            "name": ["Alice", "Bob", "Charlie"],
            "score": [95, 82, 91],
        })
        self.rows, col_defs = lazyframe_to_datagrid(lf)
        self.columns = [c.dict() for c in col_defs]

def index() -> rx.Component:
    return data_grid(
        rows=State.rows,
        columns=State.columns,
        page_size_options=[5, 10, 25],
        height="400px",
    )
```

## Features

- Wraps `@mui/x-data-grid` v8 (Community edition)
- Automatic polars dtype to DataGrid column type mapping
- `ColumnDef` model with snake_case Python attrs that auto-convert to camelCase JS props
- Event handlers for row click, cell click, sorting, filtering, pagination, and selection changes
- `WrappedDataGrid` that auto-sizes its container (MUI DataGrid requires explicit parent dimensions)
- Convenience `row_id_field` parameter for custom row identification

## API

### `data_grid(...)`

The main callable — creates a `WrappedDataGrid` (auto-sized container). Key props:

| Prop | Type | Description |
|------|------|-------------|
| `rows` | `list[dict]` | Row data |
| `columns` | `list[dict]` | Column definitions (use `ColumnDef.dict()`) |
| `row_id_field` | `str` | Field to use as row ID (default: `"id"`) |
| `height` / `width` | `str` | Container dimensions |
| `checkbox_selection` | `bool` | Show checkboxes |
| `page_size_options` | `list[int]` | Pagination options |
| `density` | `str` | `"comfortable"`, `"compact"`, or `"standard"` |
| `show_toolbar` | `bool` | Show the built-in toolbar |
| `on_row_click` | `EventHandler` | Row click callback |
| `on_sort_model_change` | `EventHandler` | Sort change callback |
| `on_pagination_model_change` | `EventHandler` | Page change callback |

### `ColumnDef(field, ...)`

Column definition (auto camelCase serialization):

```python
from reflex_mui_datagrid import ColumnDef

col = ColumnDef(
    field="salary",
    header_name="Annual Salary",
    type="number",
    flex=1,
    sortable=True,
)
```

### `lazyframe_to_datagrid(lf, *, id_field=None, limit=None)`

Convert a polars `LazyFrame` to `(rows, column_defs)`. Adds a `__row_id__` column if no `id` column exists.

## License

MIT
