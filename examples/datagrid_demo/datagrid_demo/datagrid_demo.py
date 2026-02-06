"""Example Reflex app demonstrating the MUI X DataGrid wrapper.

Two tabs:
  1. Employee data – inline polars LazyFrame with pagination.
  2. Genomic Variants (VCF) – loaded via polars-bio scan_vcf with virtual scroll.
"""

from pathlib import Path
from typing import Any

import polars as pl
import polars_bio as pb
import reflex as rx

from reflex_mui_datagrid import data_grid, lazyframe_to_datagrid

VCF_PATH: Path = Path(__file__).parent / "data" / "antku_small.vcf"


# ---------------------------------------------------------------------------
# Sample data builders
# ---------------------------------------------------------------------------

def _build_employee_lazyframe() -> pl.LazyFrame:
    """Create a sample LazyFrame with employee data."""
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

class AppState(rx.State):
    """Application state holding data for both tabs."""

    # Employee tab
    emp_rows: list[dict[str, Any]] = []
    emp_columns: list[dict[str, Any]] = []
    emp_selected: str = "Click a row to see its details."

    # VCF tab
    vcf_rows: list[dict[str, Any]] = []
    vcf_columns: list[dict[str, Any]] = []
    vcf_selected: str = "Click a variant to see its details."
    vcf_row_count: int = 0

    def load_all(self) -> None:
        """Load both datasets on page load."""
        self._load_employees()
        self._load_vcf()

    def _load_employees(self) -> None:
        lf = _build_employee_lazyframe()
        rows, col_defs = lazyframe_to_datagrid(lf)
        self.emp_rows = rows
        self.emp_columns = [c.dict() for c in col_defs]

    def _load_vcf(self) -> None:
        lf = pb.scan_vcf(str(VCF_PATH))
        rows, col_defs = lazyframe_to_datagrid(lf)
        self.vcf_rows = rows
        self.vcf_columns = [c.dict() for c in col_defs]
        self.vcf_row_count = len(rows)

    def handle_emp_row_click(self, params: dict[str, Any]) -> None:
        """Handle employee row click."""
        row = params.get("row", {})
        if row:
            name = f"{row.get('first_name', '')} {row.get('last_name', '')}"
            dept = row.get("department", "N/A")
            salary = row.get("salary", "N/A")
            self.emp_selected = (
                f"Selected: {name} | Department: {dept} | Salary: ${salary:,}"
                if isinstance(salary, (int, float))
                else f"Selected: {name} | Department: {dept} | Salary: {salary}"
            )

    def handle_vcf_row_click(self, params: dict[str, Any]) -> None:
        """Handle VCF variant row click."""
        row = params.get("row", {})
        if row:
            chrom = row.get("chrom", "?")
            start = row.get("start", "?")
            ref = row.get("ref", "")
            alt = row.get("alt", "")
            gt = row.get("GT", "")
            filt = row.get("filter", "")
            self.vcf_selected = (
                f"chr{chrom}:{start} | {ref} > {alt} | GT: {gt} | Filter: {filt}"
            )


# ---------------------------------------------------------------------------
# UI components
# ---------------------------------------------------------------------------

def _status_box(*children: rx.Component) -> rx.Component:
    """Styled status box below a grid."""
    return rx.box(
        *children,
        margin_top="1em",
        padding="1em",
        border_radius="8px",
        background="var(--gray-a3)",
    )


def employee_tab() -> rx.Component:
    """Employee data tab content."""
    return rx.box(
        rx.text(
            "A 20-row employee dataset built from an inline polars LazyFrame. "
            "Columns like Department auto-detect as dropdown filters. "
            "Uses pagination with configurable page sizes.",
            margin_bottom="1em",
            color="var(--gray-11)",
        ),
        rx.cond(
            AppState.emp_rows.length() > 0,  # type: ignore[operator]
            data_grid(
                rows=AppState.emp_rows,
                columns=AppState.emp_columns,
                row_id_field="id",
                page_size_options=[5, 10, 20],
                checkbox_selection=True,
                disable_row_selection_on_click=True,
                show_toolbar=True,
                on_row_click=AppState.handle_emp_row_click,
                height="480px",
                width="100%",
            ),
        ),
        _status_box(
            rx.text(AppState.emp_selected, weight="bold"),
        ),
        padding_top="1em",
    )


def vcf_tab() -> rx.Component:
    """Genomic variants (VCF) tab content."""
    return rx.box(
        rx.text(
            "Genomic variant calls loaded from a VCF file via ",
            rx.code("polars_bio.scan_vcf()"),
            " as a native polars LazyFrame. ",
            "Uses virtual scrolling (no pagination) for smooth browsing. ",
            "Low-cardinality columns like Filter and GT get dropdown filters automatically.",
            margin_bottom="1em",
            color="var(--gray-11)",
        ),
        rx.cond(
            AppState.vcf_rows.length() > 0,  # type: ignore[operator]
            rx.fragment(
                rx.text(
                    AppState.vcf_row_count.to(str),  # type: ignore[union-attr]
                    " variants loaded",
                    size="2",
                    color="var(--gray-9)",
                    margin_bottom="0.5em",
                ),
                data_grid(
                    rows=AppState.vcf_rows,
                    columns=AppState.vcf_columns,
                    row_id_field="__row_id__",
                    show_toolbar=True,
                    density="compact",
                    virtual_scroll=True,
                    on_row_click=AppState.handle_vcf_row_click,
                    height="540px",
                    width="100%",
                ),
            ),
        ),
        _status_box(
            rx.text(AppState.vcf_selected, weight="bold"),
        ),
        padding_top="1em",
    )


def index() -> rx.Component:
    """Render the main page with tabs."""
    return rx.box(
        rx.heading("MUI X DataGrid – Reflex Demo", size="6", margin_bottom="1em"),
        rx.tabs.root(
            rx.tabs.list(
                rx.tabs.trigger("Employee Data", value="employees"),
                rx.tabs.trigger("Genomic Variants (VCF)", value="vcf"),
            ),
            rx.tabs.content(employee_tab(), value="employees"),
            rx.tabs.content(vcf_tab(), value="vcf"),
            default_value="employees",
        ),
        padding="2em",
        max_width="1100px",
        margin="0 auto",
    )


app = rx.App()
app.add_page(index, on_load=AppState.load_all)
