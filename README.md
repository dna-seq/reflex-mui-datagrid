# reflex-mui-datagrid

Reflex wrapper for the [MUI X DataGrid](https://mui.com/x/react-data-grid/) (v8) React component, with built-in [polars](https://pola.rs/) LazyFrame support.

## Installation

```bash
uv add reflex-mui-datagrid
```

Requires Python >= 3.12, Reflex >= 0.8.26, and polars >= 1.38.0.

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
        show_toolbar=True,
        height="400px",
    )

app = rx.App()
app.add_page(index, on_load=State.load_data)
```

## Features

- Wraps `@mui/x-data-grid` v8 (Community edition) with `@mui/material` v7
- **Polars LazyFrame integration** -- `lazyframe_to_datagrid()` converts any LazyFrame to DataGrid-ready rows and column definitions in one call
- **Automatic column type detection** -- polars dtypes map to DataGrid types (`number`, `boolean`, `date`, `dateTime`, `string`)
- **Automatic dropdown filters** -- low-cardinality string columns and `Categorical`/`Enum` dtypes become `singleSelect` columns with dropdown filters
- **JSON-safe serialization** -- temporal columns become ISO strings, `List` columns become comma-joined strings, `Struct` columns become strings
- **`ColumnDef` model** with snake_case Python attrs that auto-convert to camelCase JS props
- **Event handlers** for row click, cell click, sorting, filtering, pagination, and row selection
- **Virtual scroll mode** -- `virtual_scroll=True` sets page size to 100 (Community max) for smooth scrolling through large datasets
- **Auto-sized container** -- `WrappedDataGrid` wraps the grid in a `<div>` with configurable `width`/`height`
- **Row identification** -- `row_id_field` parameter for custom row ID, auto-generated `__row_id__` column when no `id` column exists

## Polars-bio VCF Example

The included example app demonstrates loading genomic variant data from a VCF file using [polars-bio](https://biodatageeks.org/polars-bio/):

```python
import polars_bio as pb
from reflex_mui_datagrid import data_grid, lazyframe_to_datagrid

lf = pb.scan_vcf("variants.vcf")  # returns a polars LazyFrame
rows, col_defs = lazyframe_to_datagrid(lf)

data_grid(
    rows=State.rows,
    columns=State.columns,
    virtual_scroll=True,       # 100 rows per page, smooth scrolling
    show_toolbar=True,
    density="compact",
    height="540px",
)
```

## Running the Example

The project uses [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/). You can run the example app directly from the root:

```bash
# Install all dependencies
uv sync

# Run the demo from the root
uv run --directory examples/datagrid_demo reflex run
```

The demo has two tabs:
1. **Employee Data** -- inline polars LazyFrame with pagination, sorting, and dropdown filters
2. **Genomic Variants (VCF)** -- 793 variants loaded via `polars_bio.scan_vcf()` with virtual scrolling

## API Reference

See [docs/api.md](docs/api.md) for the full API reference.

## License

MIT
