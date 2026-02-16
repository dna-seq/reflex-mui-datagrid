"""Example Reflex app demonstrating the MUI X DataGrid wrapper.

Four tabs:
  1. Employee data -- scrollable grid (no pagination), using the universal
     ``lazyframe_to_datagrid`` (no polars-bio dependency).
  2. Genomic Variants (VCF) -- loaded via polars-bio ``scan_vcf``, using
     ``bio_lazyframe_to_datagrid`` which auto-extracts column descriptions
     from the VCF header.  Uses the small sample VCF.
  3. Longevity Map (Parquet) -- loads a parquet file from HuggingFace via
     polars' native ``hf://`` protocol.  Demonstrates that the DataGrid
     component generalises beyond VCF to arbitrary tabular data.
  4. Full Genome (Server-Side) -- demonstrates scroll-driven infinite
     loading, filtering, and sorting on a ~4.5 M row whole-genome VCF
     using the reusable ``LazyFrameGridMixin`` and ``lazyframe_grid()``.
"""

from pathlib import Path
from typing import Any

import polars as pl
import polars_bio as pb
import reflex as rx

from reflex_mui_datagrid import (
    LazyFrameGridMixin,
    bio_lazyframe_to_datagrid,
    data_grid,
    extract_vcf_descriptions,
    lazyframe_grid,
    lazyframe_grid_code_panel,
    lazyframe_grid_detail_box,
    lazyframe_grid_stats_bar,
    lazyframe_to_datagrid,
    scan_file,
)

VCF_PATH: Path = Path(__file__).parent / "data" / "antku_small.vcf"

# Pre-compute VCF column descriptions at module level so both
# the data loader and the row-click handler can use them.
_vcf_lf_for_meta: pl.LazyFrame = pb.scan_vcf(str(VCF_PATH))
VCF_DESCRIPTIONS: dict[str, str] = extract_vcf_descriptions(_vcf_lf_for_meta)
del _vcf_lf_for_meta  # don't hold onto the LazyFrame


# ---------------------------------------------------------------------------
# Full-genome constants
# ---------------------------------------------------------------------------

GENOME_URL: str = "https://zenodo.org/records/18370498/files/antonkulaga.vcf?download=1"
GENOME_PATH: Path = Path(__file__).parent / "data" / "antonkulaga.vcf"

# ---------------------------------------------------------------------------
# Parquet (HuggingFace) constants
# ---------------------------------------------------------------------------

PARQUET_HF_URL: str = "hf://datasets/just-dna-seq/annotators/data/longevitymap/weights.parquet"


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

class AppState(LazyFrameGridMixin):
    """Application state holding data for all tabs.

    Inherits from ``LazyFrameGridMixin`` (which extends ``rx.State``)
    to get server-side scroll-loading state vars and handlers
    (prefixed ``lf_grid_*``) for the genome tab.
    """

    # Employee tab
    emp_rows: list[dict[str, Any]] = []
    emp_columns: list[dict[str, Any]] = []
    emp_selected: str = "Click a row to see its details."

    # VCF tab
    vcf_rows: list[dict[str, Any]] = []
    vcf_columns: list[dict[str, Any]] = []
    vcf_selected: str = "Click a variant to see its details."
    vcf_row_count: int = 0

    # Parquet tab
    pq_rows: list[dict[str, Any]] = []
    pq_columns: list[dict[str, Any]] = []
    pq_selected: str = "Click a row to see its details."
    pq_row_count: int = 0
    pq_loading: bool = False
    pq_loaded: bool = False
    pq_error: str = ""

    # Genome tab (only need availability flag -- everything else is in the mixin)
    genome_available: bool = False

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def load_all(self) -> None:
        """Load both small datasets on page load."""
        self._load_employees()
        self._load_vcf()
        self.genome_available = GENOME_PATH.exists()

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

    # ------------------------------------------------------------------
    # Employee handlers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Small VCF handlers
    # ------------------------------------------------------------------

    def handle_vcf_row_click(self, params: dict[str, Any]) -> None:
        """Handle VCF variant row click -- show all fields with descriptions."""
        row: dict[str, Any] = params.get("row", {})
        if not row:
            return

        lines: list[str] = []
        for field, value in row.items():
            if field == "__row_id__":
                continue
            desc = VCF_DESCRIPTIONS.get(field, "")
            if desc:
                lines.append(f"{field}: {value}  ({desc})")
            else:
                lines.append(f"{field}: {value}")
        self.vcf_selected = "\n".join(lines)

    # ------------------------------------------------------------------
    # Parquet (HuggingFace) handlers
    # ------------------------------------------------------------------

    def load_parquet(self):
        """Load the longevity-map parquet from HuggingFace via polars ``hf://``.

        Uses polars' native HuggingFace integration -- no fsspec needed.
        This is a generator so the loading spinner shows immediately.
        """
        self.pq_loading = True  # type: ignore[assignment]
        self.pq_error = ""  # type: ignore[assignment]
        yield  # send loading state to frontend

        lf = pl.scan_parquet(PARQUET_HF_URL)
        rows, col_defs = lazyframe_to_datagrid(lf)
        self.pq_rows = rows
        self.pq_columns = [c.dict() for c in col_defs]
        self.pq_row_count = len(rows)
        self.pq_loading = False  # type: ignore[assignment]
        self.pq_loaded = True  # type: ignore[assignment]

    def handle_pq_row_click(self, params: dict[str, Any]) -> None:
        """Handle parquet row click -- show all fields."""
        row: dict[str, Any] = params.get("row", {})
        if not row:
            return

        lines: list[str] = []
        for field, value in row.items():
            if field == "__row_id__":
                continue
            lines.append(f"{field}: {value}")
        self.pq_selected = "\n".join(lines)

    # ------------------------------------------------------------------
    # Full genome (server-side via LazyFrameGridMixin)
    # ------------------------------------------------------------------

    def load_genome(self):
        """Prepare the full genome VCF for server-side browsing.

        Uses ``scan_file`` + ``set_lazyframe`` from the mixin -- the
        LazyFrame is never fully collected into memory.
        """
        if not GENOME_PATH.exists():
            self.lf_grid_selected_info = (
                "Genome file not found. "
                "Run: uv run demo download-genome"
            )
            return

        lf, descriptions = scan_file(GENOME_PATH)
        yield from self.set_lazyframe(lf, descriptions)


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
            "No pagination -- all rows are scrollable.",
            margin_bottom="1em",
            color="var(--gray-11)",
        ),
        rx.cond(
            AppState.emp_rows.length() > 0,  # type: ignore[operator]
            data_grid(
                rows=AppState.emp_rows,
                columns=AppState.emp_columns,
                row_id_field="id",
                pagination=False,
                hide_footer=True,
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
            ". Hover over a column header to see its description. "
            "No pagination -- all rows are scrollable (MUI's built-in row "
            "virtualisation only renders visible DOM rows). "
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
                    pagination=False,
                    hide_footer=True,
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


def parquet_tab() -> rx.Component:
    """Longevity Map parquet tab content."""
    return rx.box(
        rx.text(
            "Longevity-map weights loaded from a ",
            rx.link(
                "HuggingFace parquet file",
                href="https://huggingface.co/datasets/just-dna-seq/annotators/blob/main/data/longevitymap/weights.parquet",
            ),
            " via polars' native ",
            rx.code("hf://"),
            " protocol -- no fsspec or manual download needed. "
            "Demonstrates that the DataGrid component generalises to "
            "arbitrary tabular data beyond VCF files.",
            margin_bottom="1em",
            color="var(--gray-11)",
        ),
        rx.cond(
            AppState.pq_loaded,
            # Data loaded -- show grid
            rx.fragment(
                rx.text(
                    AppState.pq_row_count.to(str),  # type: ignore[union-attr]
                    " rows loaded from HuggingFace",
                    size="2",
                    color="var(--gray-9)",
                    margin_bottom="0.5em",
                ),
                data_grid(
                    rows=AppState.pq_rows,
                    columns=AppState.pq_columns,
                    row_id_field="__row_id__",
                    pagination=False,
                    hide_footer=True,
                    show_toolbar=True,
                    density="compact",
                    on_row_click=AppState.handle_pq_row_click,
                    height="540px",
                    width="100%",
                ),
            ),
            # Not loaded yet -- show load button
            rx.box(
                rx.button(
                    "Load Parquet from HuggingFace",
                    on_click=AppState.load_parquet,
                    loading=AppState.pq_loading,
                    size="3",
                ),
                rx.text(
                    "Click to fetch the longevity-map weights parquet (~26 KB) "
                    "directly from HuggingFace using polars' native hf:// protocol.",
                    size="2",
                    color="var(--gray-9)",
                    margin_top="0.5em",
                ),
                rx.cond(
                    AppState.pq_error != "",
                    rx.callout(
                        AppState.pq_error,
                        icon="triangle_alert",
                        color_scheme="red",
                        margin_top="1em",
                    ),
                ),
            ),
        ),
        _status_box(
            rx.text(
                AppState.pq_selected,
                white_space="pre-wrap",
                size="2",
            ),
        ),
        padding_top="1em",
    )


def _genome_download_box() -> rx.Component:
    """Instructions shown when the genome VCF is not yet downloaded."""
    return rx.box(
        rx.text("Genome file not downloaded yet.", weight="bold"),
        rx.text(
            "Run ",
            rx.code("uv run demo download-genome"),
            " to download the full genome (~483 MB from ",
            rx.link("Zenodo", href="https://zenodo.org/records/18370498"),
            "), then refresh this page.",
        ),
        padding="1.5em",
        border_radius="8px",
        background="var(--amber-3)",
        border="1px solid var(--amber-7)",
    )


def _genome_load_button() -> rx.Component:
    """Button shown when genome file exists but hasn't been loaded yet."""
    return rx.box(
        rx.button(
            "Load Genome",
            on_click=AppState.load_genome,
            loading=AppState.lf_grid_loading,
            size="3",
        ),
        rx.text(
            "Click to prepare the full human genome VCF for lazy server-side browsing. "
            "Only small slices are collected per request.",
            size="2",
            color="var(--gray-9)",
            margin_top="0.5em",
        ),
    )


def _genome_grid() -> rx.Component:
    """The scroll-loading DataGrid for the genome, powered by the mixin."""
    return rx.fragment(
        lazyframe_grid_stats_bar(AppState),
        lazyframe_grid(AppState),
        lazyframe_grid_code_panel(AppState),
    )


def genome_tab() -> rx.Component:
    """Full genome (scroll-loading) tab content."""
    return rx.box(
        rx.text(
            "Full human genome (~4.5 M variants) with ",
            rx.text("server-side", weight="bold", as_="span"),
            " scroll-loading, filtering, and sorting. "
            "Rows are loaded in chunks as you scroll near the bottom. "
            "Filter and sort operations run as Polars expressions on the "
            "backend -- no full-table collect for each interaction.",
            margin_bottom="1em",
            color="var(--gray-11)",
        ),
        rx.cond(
            AppState.genome_available,
            # File exists
            rx.cond(
                AppState.lf_grid_loaded,
                _genome_grid(),
                _genome_load_button(),
            ),
            # File not downloaded
            _genome_download_box(),
        ),
        lazyframe_grid_detail_box(AppState),
        padding_top="1em",
    )


def index() -> rx.Component:
    """Render the main page with tabs."""
    return rx.box(
        rx.heading("MUI X DataGrid -- Reflex Demo", size="6", margin_bottom="1em"),
        rx.tabs.root(
            rx.tabs.list(
                rx.tabs.trigger("Employee Data", value="employees"),
                rx.tabs.trigger("Genomic Variants (VCF)", value="vcf"),
                rx.tabs.trigger("Longevity Map (Parquet)", value="parquet"),
                rx.tabs.trigger("Full Genome (Server-Side)", value="genome"),
            ),
            rx.tabs.content(employee_tab(), value="employees"),
            rx.tabs.content(vcf_tab(), value="vcf"),
            rx.tabs.content(parquet_tab(), value="parquet"),
            rx.tabs.content(genome_tab(), value="genome"),
            default_value="parquet",
        ),
        padding="2em",
        max_width="1400px",
        margin="0 auto",
    )


app = rx.App()
app.add_page(index, on_load=AppState.load_all)
