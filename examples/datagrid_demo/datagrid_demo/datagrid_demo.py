"""Example Reflex app demonstrating the MUI X DataGrid wrapper with polars LazyFrame."""

from typing import Any

import polars as pl
import reflex as rx

from reflex_mui_datagrid import ColumnDef, data_grid, lazyframe_to_datagrid


# ---------------------------------------------------------------------------
# Sample data – a polars LazyFrame with mixed types
# ---------------------------------------------------------------------------

def _build_sample_lazyframe() -> pl.LazyFrame:
    """Create a sample LazyFrame with employee data for demonstration."""
    return pl.LazyFrame(
        {
            "id": list(range(1, 21)),
            "first_name": [
                "Alice", "Bob", "Charlie", "Diana", "Eve",
                "Frank", "Grace", "Hank", "Ivy", "Jack",
                "Karen", "Leo", "Mona", "Nick", "Olivia",
                "Paul", "Quinn", "Rita", "Sam", "Tina",
            ],
            "last_name": [
                "Smith", "Johnson", "Williams", "Brown", "Jones",
                "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
                "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
                "Thomas", "Taylor", "Moore", "Jackson", "Martin",
            ],
            "department": [
                "Engineering", "Marketing", "Engineering", "Sales", "Engineering",
                "Marketing", "Sales", "Engineering", "Marketing", "Sales",
                "Engineering", "Marketing", "Sales", "Engineering", "Marketing",
                "Sales", "Engineering", "Marketing", "Sales", "Engineering",
            ],
            "salary": [
                95000, 72000, 110000, 68000, 125000,
                71000, 82000, 98000, 67000, 78000,
                105000, 69000, 74000, 115000, 73000,
                80000, 99000, 70000, 76000, 108000,
            ],
            "active": [
                True, True, True, False, True,
                True, False, True, True, True,
                True, False, True, True, True,
                False, True, True, False, True,
            ],
        }
    )


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class DataGridState(rx.State):
    """Application state holding grid data and interaction results."""

    rows: list[dict[str, Any]] = []
    columns: list[dict[str, Any]] = []
    selected_row_info: str = "Click a row to see its details."
    sort_info: str = "No sorting applied."
    pagination_info: str = "Page 1"

    def load_data(self) -> None:
        """Load data from a polars LazyFrame into the grid."""
        lf = _build_sample_lazyframe()
        rows, col_defs = lazyframe_to_datagrid(lf)
        self.rows = rows
        self.columns = [c.dict() for c in col_defs]

    def handle_row_click(self, params: dict[str, Any]) -> None:
        """Handle a row click event from the DataGrid."""
        row = params.get("row", {})
        if row:
            name = f"{row.get('first_name', '')} {row.get('last_name', '')}"
            dept = row.get("department", "N/A")
            salary = row.get("salary", "N/A")
            self.selected_row_info = (
                f"Selected: {name} | Department: {dept} | Salary: ${salary:,}"
                if isinstance(salary, (int, float))
                else f"Selected: {name} | Department: {dept} | Salary: {salary}"
            )

    def handle_sort_change(self, model: list[dict[str, Any]]) -> None:
        """Handle sort model change."""
        if model:
            parts = [f"{m.get('field')} ({m.get('sort', 'none')})" for m in model]
            self.sort_info = f"Sorted by: {', '.join(parts)}"
        else:
            self.sort_info = "No sorting applied."

    def handle_pagination_change(self, model: dict[str, Any]) -> None:
        """Handle pagination model change."""
        page = model.get("page", 0) + 1  # MUI uses 0-based pages
        page_size = model.get("pageSize", 5)
        self.pagination_info = f"Page {page} (showing {page_size} rows)"


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def index() -> rx.Component:
    """Render the main page."""
    return rx.box(
        rx.heading("MUI X DataGrid – Reflex Demo", size="6", margin_bottom="1em"),
        rx.text(
            "This example loads a polars LazyFrame and renders it "
            "using the MUI X DataGrid wrapper.",
            margin_bottom="1em",
        ),
        rx.button(
            "Load Data",
            on_click=DataGridState.load_data,
            margin_bottom="1em",
            size="3",
        ),
        # DataGrid with event handlers
        rx.cond(
            DataGridState.rows.length() > 0,  # type: ignore[operator]
            data_grid(
                rows=DataGridState.rows,
                columns=DataGridState.columns,
                row_id_field="id",
                page_size_options=[5, 10, 20],
                checkbox_selection=True,
                disable_row_selection_on_click=True,
                on_row_click=DataGridState.handle_row_click,
                on_sort_model_change=DataGridState.handle_sort_change,
                on_pagination_model_change=DataGridState.handle_pagination_change,
                height="450px",
                width="100%",
            ),
        ),
        # Status area
        rx.box(
            rx.text(DataGridState.selected_row_info, weight="bold"),
            rx.text(DataGridState.sort_info),
            rx.text(DataGridState.pagination_info),
            margin_top="1em",
            padding="1em",
            border_radius="8px",
            background="var(--gray-a3)",
        ),
        padding="2em",
        max_width="1000px",
        margin="0 auto",
    )


app = rx.App()
app.add_page(index, on_load=DataGridState.load_data)
