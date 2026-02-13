"""Example Reflex app demonstrating the MUI X DataGrid wrapper.

Two tabs:
  1. Employee data – scrollable grid (no pagination), using the universal
     ``lazyframe_to_datagrid`` (no polars-bio dependency).
  2. Genomic Variants (VCF) – loaded via polars-bio ``scan_vcf``, using
     ``bio_lazyframe_to_datagrid`` which auto-extracts column descriptions
     from the VCF header.
"""

from pathlib import Path
from typing import Any

import polars as pl
import polars_bio as pb
import reflex as rx

from reflex_mui_datagrid import (
    bio_lazyframe_to_datagrid,
    data_grid,
    extract_vcf_descriptions,
    lazyframe_to_datagrid,
)

VCF_PATH: Path = Path(__file__).parent / "data" / "antku_small.vcf"

# Pre-compute VCF column descriptions at module level so both
# the data loader and the row-click handler can use them.
_vcf_lf_for_meta: pl.LazyFrame = pb.scan_vcf(str(VCF_PATH))
VCF_DESCRIPTIONS: dict[str, str] = extract_vcf_descriptions(_vcf_lf_for_meta)
del _vcf_lf_for_meta  # don't hold onto the LazyFrame


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
        rows, col_defs = bio_lazyframe_to_datagrid(lf)
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
        """Handle VCF variant row click – show all fields with descriptions."""
        row: dict[str, Any] = params.get("row", {})
        if not row:
            return

        # Build a multi-line detail string with all fields.
        lines: list[str] = []
        for field, value in row.items():
            # Skip the synthetic row-id column.
            if field == "__row_id__":
                continue
            desc = VCF_DESCRIPTIONS.get(field, "")
            if desc:
                lines.append(f"{field}: {value}  ({desc})")
            else:
                lines.append(f"{field}: {value}")
        self.vcf_selected = "\n".join(lines)


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
            "No pagination – all rows are scrollable.",
            margin_bottom="1em",
            color="var(--gray-11)",
        ),
        rx.cond(
            AppState.emp_rows.length() > 0,  # type: ignore[operator]
            data_grid(
                rows=AppState.emp_rows,
                columns=AppState.emp_columns,
                row_id_field="id",
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
            " as a native polars LazyFrame, with column descriptions "
            "auto-extracted via ",
            rx.code("bio_lazyframe_to_datagrid()"),
            ". Hover over a column header to see its description. ",
            "No pagination – all rows are scrollable (MUI's built-in row "
            "virtualisation only renders visible DOM rows). ",
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
                    show_description_in_header=True,
                    density="compact",
                    column_header_height=70,
                    on_row_click=AppState.handle_vcf_row_click,
                    height="540px",
                    width="100%",
                ),
            ),
        ),
        _status_box(
            rx.text(
                AppState.vcf_selected,
                white_space="pre-wrap",
                size="2",
            ),
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
            default_value="vcf",
        ),
        padding="2em",
        max_width="1100px",
        margin="0 auto",
    )


app = rx.App()
app.add_page(index, on_load=AppState.load_all)
