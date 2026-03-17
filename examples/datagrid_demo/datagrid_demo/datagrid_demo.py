"""Example Reflex app demonstrating the MUI X DataGrid wrapper.

Four tabs:
  1. Employee data -- small client-side scrollable grid (no pagination).
  2. Genomic Variants (VCF) -- small client-side VCF grid with
     auto-extracted column descriptions.
  3. Longevity Map (Parquet) -- **server-side** lazy grid loaded from
     HuggingFace via ``hf://``.  Uses ``LazyFrameGridMixin`` for
     server-side filtering, sorting, and scroll-loading.
  4. Full Genome (Server-Side) -- ~4.5 M row whole-genome VCF with
     server-side scroll-loading via a second ``LazyFrameGridMixin``.

Tabs 3 and 4 each use their own ``LazyFrameGridMixin`` substate so
they get independent ``lf_grid_*`` state vars and caches.
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

PARQUET_HF_URL: str = (
    "hf://datasets/just-dna-seq/annotators/data/longevitymap/weights.parquet"
)


# ---------------------------------------------------------------------------
# Sample data builders
# ---------------------------------------------------------------------------


def _build_interpretation(
    trait: str,
    percentile: float,
    population: str,
    pct_method: str,
    auroc: float | None,
    match_rate: float,
) -> str:
    """Generate a realistic PRS interpretation paragraph."""
    if percentile < 25:
        risk_level = "below average predisposition"
        risk_tag = "Below average predisposition"
    elif percentile < 75:
        risk_level = "average predisposition"
        risk_tag = "Average predisposition"
    else:
        risk_level = "above average predisposition"
        risk_tag = "Above average predisposition"

    ordinal = f"{int(percentile)}th" if percentile != 1 else "1st"
    auroc_str = f"AUROC={auroc:.3f}" if auroc else "No AUROC available to assess model accuracy"

    return (
        f"Your PRS for {trait} is at the {ordinal} percentile "
        f"-- {risk_level} compared to the {population} reference population. "
        f"For standard PRS models, higher percentile = more genetic variants "
        f"associated with increased risk. Reference distributions source: "
        f"local percentiles cache. These are precomputed from reference panel "
        f"scoring and are not provided directly by the PGS Catalog API."
    ), risk_tag, (
        f"Estimated percentile: {percentile}% ({pct_method}, from allele frequencies "
        f"in the scoring file). {auroc_str}. "
        f"{match_rate:.0f}% of scoring variants matched."
    ), (
        "Reference source: local percentiles cache. These precomputed distributions "
        "are generated from reference panel scoring (not direct PGS Catalog score "
        "API percentiles)."
    )


def _build_prs_lazyframe() -> pl.LazyFrame:
    import random

    random.seed(42)

    prs_records = [
        {"pgs_id": "PGS000028", "trait": "Breast cancer", "score": 3.607,
         "pct": 0.0, "pop": "East Asian, European, Hispanic or Latin American",
         "method": "theoretical", "auroc": 0.6, "quality": "Moderate",
         "match": 62.0},
        {"pgs_id": "PGS000056", "trait": "Parkinson's disease", "score": 1.625,
         "pct": 0.0, "pop": "European",
         "method": "theoretical", "auroc": None, "quality": "Moderate",
         "match": 52.0},
        {"pgs_id": "PGS001781", "trait": "Type 2 diabetes (T2D)", "score": 0.035,
         "pct": 51.3, "pop": "European",
         "method": "theoretical", "auroc": 0.725, "quality": "High",
         "match": 63.0},
        {"pgs_id": "PGS002760", "trait": "Epilepsy", "score": -1.141,
         "pct": 0.0, "pop": "European",
         "method": "theoretical", "auroc": None, "quality": "Moderate",
         "match": 45.0},
        {"pgs_id": "PGS003470", "trait": "HOMA-IR", "score": -0.053,
         "pct": 0.0, "pop": "Hispanic or Latin American",
         "method": "theoretical", "auroc": None, "quality": "Moderate",
         "match": 38.0},
    ]

    more_traits = [
        ("PGS000017", "Coronary artery disease", 2.145, 68.2, "European", "1000G ref", 0.612, "High", 71.0),
        ("PGS000039", "Rheumatoid arthritis", -0.832, 15.4, "European", "theoretical", 0.581, "Moderate", 55.0),
        ("PGS000074", "Systemic lupus erythematosus", 1.902, 82.7, "East Asian", "theoretical", None, "Low", 42.0),
        ("PGS000091", "Atrial fibrillation", 0.567, 61.0, "European", "1000G ref", 0.710, "High", 68.0),
        ("PGS000182", "Hypertension", -1.340, 8.3, "European", "theoretical", 0.598, "Moderate", 59.0),
        ("PGS000329", "Stroke", 0.234, 54.1, "European", "theoretical", None, "Low", 47.0),
        ("PGS000401", "Prostate cancer", 3.891, 95.2, "European", "1000G ref", 0.780, "High", 74.0),
        ("PGS000512", "Alzheimer's disease", -0.178, 42.6, "European", "theoretical", 0.630, "Moderate", 51.0),
        ("PGS000618", "Asthma", 1.056, 71.8, "European", "theoretical", 0.550, "Low", 48.0),
        ("PGS000789", "Major depressive disorder", -0.445, 31.2, "European", "1000G ref", None, "Low", 39.0),
    ]
    for pgs_id, trait, score, pct, pop, method, auroc, quality, match in more_traits:
        prs_records.append({
            "pgs_id": pgs_id, "trait": trait, "score": score,
            "pct": pct, "pop": pop,
            "method": method, "auroc": auroc, "quality": quality,
            "match": match,
        })

    populations = ["AFR", "AMR", "EAS", "EUR", "SAS"]
    data = []
    for rec in prs_records:
        interpretation, risk_tag, est_pct, ref_source = _build_interpretation(
            rec["trait"], rec["pct"], rec["pop"],
            rec["method"], rec["auroc"], rec["match"],
        )
        pop_values = {}
        for p in populations:
            pop_values[p] = round(random.uniform(0, 100), 1) if random.random() > 0.4 else ""

        row = {
            "PGS ID": rec["pgs_id"],
            "Trait": rec["trait"],
            "PRS Score": rec["score"],
            "Percentile": rec["pct"],
            **{p: v for p, v in pop_values.items()},
            "Pct. Method": rec["method"],
            "AUROC": rec["auroc"] if rec["auroc"] is not None else "",
            "Quality": rec["quality"],
            "Match Rate": rec["match"],
            "Population": rec["pop"],
            # Hidden detail-only fields:
            "risk_hint": f"{rec['pgs_id']}  |  {risk_tag}  |  Quality: {rec['quality']}  |  Pop: {rec['pop']}  |  Ref: precomputed (AFR, AMR, EAS, EUR, SAS)",
            "interpretation": interpretation,
            "estimated_percentile": est_pct,
            "reference_source": ref_source,
        }
        data.append(row)
    return pl.LazyFrame(data)


def _build_employee_lazyframe() -> pl.LazyFrame:
    """Create a sample LazyFrame with employee data."""
    return pl.LazyFrame(
        {
            "id": list(range(1, 21)),
            "first_name": [
                "Alice",
                "Bob",
                "Charlie",
                "Diana",
                "Eve",
                "Frank",
                "Grace",
                "Hank",
                "Ivy",
                "Jack",
                "Karen",
                "Leo",
                "Mona",
                "Nick",
                "Olivia",
                "Paul",
                "Quinn",
                "Rita",
                "Sam",
                "Tina",
            ],
            "last_name": [
                "Smith",
                "Johnson",
                "Williams",
                "Brown",
                "Jones",
                "Garcia",
                "Miller",
                "Davis",
                "Rodriguez",
                "Martinez",
                "Hernandez",
                "Lopez",
                "Gonzalez",
                "Wilson",
                "Anderson",
                "Thomas",
                "Taylor",
                "Moore",
                "Jackson",
                "Martin",
            ],
            "department": [
                "Engineering",
                "Marketing",
                "Engineering",
                "Sales",
                "Engineering",
                "Marketing",
                "Sales",
                "Engineering",
                "Marketing",
                "Sales",
                "Engineering",
                "Marketing",
                "Sales",
                "Engineering",
                "Marketing",
                "Sales",
                "Engineering",
                "Marketing",
                "Sales",
                "Engineering",
            ],
            "salary": [
                95000,
                72000,
                110000,
                68000,
                125000,
                71000,
                82000,
                98000,
                67000,
                78000,
                105000,
                69000,
                74000,
                115000,
                73000,
                80000,
                99000,
                70000,
                76000,
                108000,
            ],
            "active": [
                True,
                True,
                True,
                False,
                True,
                True,
                False,
                True,
                True,
                True,
                True,
                False,
                True,
                True,
                True,
                False,
                True,
                True,
                False,
                True,
            ],
        }
    )


# ---------------------------------------------------------------------------
# Substates for server-side grids
# ---------------------------------------------------------------------------


class ParquetState(LazyFrameGridMixin, rx.State):
    """Server-side lazy grid for the Longevity Map parquet dataset.

    Each ``LazyFrameGridMixin`` substate gets its own independent set
    of ``lf_grid_*`` state vars and its own LazyFrame cache (keyed by
    class name).
    """

    pq_loaded: bool = False
    pq_loading_init: bool = False

    def load_parquet(self):
        """Scan the parquet from HuggingFace and prepare for lazy browsing."""
        self.pq_loading_init = True  # type: ignore[assignment]
        yield

        lf = pl.scan_parquet(PARQUET_HF_URL)
        yield from self.set_lazyframe(lf)
        self.pq_loaded = True  # type: ignore[assignment]
        self.pq_loading_init = False  # type: ignore[assignment]


class GenomeState(LazyFrameGridMixin, rx.State):
    """Server-side lazy grid for the full genome VCF (~4.5 M rows).

    Each ``LazyFrameGridMixin`` substate gets its own independent set
    of ``lf_grid_*`` state vars and its own LazyFrame cache.
    """

    genome_available: bool = False

    def check_genome(self) -> None:
        """Check if the genome file exists on disk."""
        self.genome_available = GENOME_PATH.exists()

    def load_genome(self):
        """Scan the genome VCF and prepare for lazy browsing."""
        if not GENOME_PATH.exists():
            self.lf_grid_selected_info = (  # type: ignore[assignment]
                "Genome file not found. Run: uv run demo download-genome"
            )
            return

        lf, descriptions = scan_file(GENOME_PATH)
        yield from self.set_lazyframe(lf, descriptions)


# ---------------------------------------------------------------------------
# Main app state (client-side grids only)
# ---------------------------------------------------------------------------


class AppState(rx.State):
    """Application state holding data for the small client-side tabs.

    The Parquet and Genome tabs use their own ``LazyFrameGridMixin``
    substates (``ParquetState`` and ``GenomeState``).
    """

    # PRS tab
    prs_rows: list[dict[str, Any]] = []
    prs_columns: list[dict[str, Any]] = []
    prs_selected: str = "Click a row to see its details."
    prs_row_count: int = 0

    # Employee tab
    emp_rows: list[dict[str, Any]] = []
    emp_columns: list[dict[str, Any]] = []
    emp_selected: str = "Click a row to see its details."

    # VCF tab
    vcf_rows: list[dict[str, Any]] = []
    vcf_columns: list[dict[str, Any]] = []
    vcf_selected: str = "Click a variant to see its details."
    vcf_row_count: int = 0

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def load_all(self) -> None:
        """Load the small client-side datasets on page load."""
        self._load_employees()
        self._load_vcf()
        self._load_prs()

    def _load_prs(self) -> None:
        lf = _build_prs_lazyframe()
        rows, col_defs = lazyframe_to_datagrid(lf)

        # Fields shown only in the expandable detail panel, not as grid columns.
        detail_only_fields = {
            "risk_hint", "interpretation", "estimated_percentile",
            "reference_source", "Population",
        }

        population_colors: dict[str, tuple[str, str]] = {
            "AFR": ("#f57f17", "#fff9c4"),
            "AMR": ("#d81b60", "#f8bbd0"),
            "EAS": ("#388e3c", "#c8e6c9"),
            "EUR": ("#1976d2", "#bbdefb"),
            "SAS": ("#8e24aa", "#e1bee7"),
        }

        visible_col_defs = []
        for col in col_defs:
            if col.field in detail_only_fields:
                continue
            if col.field == "Percentile":
                col.cell_renderer_type = "progress_bar"
                col.cell_renderer_config = {
                    "color": "#1976d2",
                    "trackColor": "#e0e0e0",
                    "showValue": True,
                }
            elif col.field in population_colors:
                c, bg = population_colors[col.field]
                col.cell_renderer_type = "badge"
                col.cell_renderer_config = {"color": c, "bgColor": bg}
            elif col.field == "Pct. Method":
                col.cell_renderer_type = "badge"
                col.cell_renderer_config = {"color": "#1976d2", "bgColor": "#e3f2fd"}
            elif col.field == "Quality":
                col.cell_renderer_type = "badge"
                col.cell_renderer_config = {
                    "colorMap": {
                        "High": "#2e7d32",
                        "Moderate": "#f57f17",
                        "Low": "#c62828",
                    },
                    "bgColorMap": {
                        "High": "#e8f5e9",
                        "Moderate": "#fff3e0",
                        "Low": "#ffebee",
                    },
                }
            elif col.field == "Match Rate":
                col.cell_renderer_type = "progress_bar"
                col.cell_renderer_config = {
                    "color": "#43a047",
                    "trackColor": "#e8e8e8",
                    "showValue": True,
                }
            visible_col_defs.append(col)

        self.prs_rows = rows
        self.prs_columns = [c.dict() for c in visible_col_defs]
        self.prs_row_count = len(rows)

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

    def handle_prs_row_click(self, params: dict[str, Any]) -> None:
        row = params.get("row", {})
        if row:
            pgs = row.get("PGS ID", "")
            trait = row.get("Trait", "")
            quality = row.get("Quality", "")
            pct = row.get("Percentile", "")
            self.prs_selected = (
                f"Selected: {pgs} -- {trait} | "
                f"Percentile: {pct}% | Quality: {quality} | "
                f"Expand the row to see the full interpretation."
            )

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


def prs_tab() -> rx.Component:
    """PRS Results tab content with expandable interpretation detail panels."""
    return rx.box(
        rx.text(
            "Polygenic Risk Score results with ",
            rx.text("expandable detail panels", weight="bold", as_="span"),
            ". Click the ",
            rx.text("\u25B6", as_="span", weight="bold"),
            " chevron on any row to reveal the full PRS interpretation, "
            "estimated percentile breakdown, and reference source -- "
            "information that would clutter the grid as columns but is "
            "essential for understanding each score. "
            "Badges and progress bars highlight key values.",
            margin_bottom="1em",
            color="var(--gray-11)",
        ),
        rx.cond(
            AppState.prs_rows.length() > 0,
            data_grid(
                rows=AppState.prs_rows,
                columns=AppState.prs_columns,
                row_id_field="PGS ID",
                pagination=False,
                hide_footer=True,
                checkbox_selection=True,
                disable_row_selection_on_click=True,
                on_row_click=AppState.handle_prs_row_click,
                detail_columns=[
                    "risk_hint",
                    "interpretation",
                    "estimated_percentile",
                    "reference_source",
                ],
                detail_labels={
                    "risk_hint": "Summary",
                    "interpretation": "Interpretation",
                    "estimated_percentile": "Estimated Percentile",
                    "reference_source": "Reference Source",
                },
                detail_badge_fields=["risk_hint"],
                detail_height=200,
                height="600px",
            ),
            rx.text("Loading data...", color="var(--gray-9)", font_style="italic"),
        ),
        rx.box(
            rx.text(AppState.prs_selected, weight="bold"),
            margin_top="1em",
            padding="1em",
            border_radius="8px",
            background="var(--gray-3)",
        ),
        height="800px",
        display="flex",
        flex_direction="column",
        gap="1em",
    )


def employee_tab() -> rx.Component:
    """Employee data tab content."""
    return rx.box(
        rx.text(
            "A 20-row employee dataset built from an inline polars LazyFrame. "
            "Columns like Department auto-detect as dropdown filters. "
            "No pagination -- all rows are scrollable. "
            "Client-side filtering (MUI Community: single filter at a time).",
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
            "Client-side filtering (MUI Community: single filter at a time).",
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
    """Longevity Map parquet tab -- server-side via ParquetState."""
    return rx.box(
        rx.text(
            "Longevity-map weights loaded from a ",
            rx.link(
                "HuggingFace parquet file",
                href="https://huggingface.co/datasets/just-dna-seq/annotators/blob/main/data/longevitymap/weights.parquet",
            ),
            " via polars' native ",
            rx.code("hf://"),
            " protocol -- no fsspec or manual download needed. ",
            rx.text("Server-side", weight="bold", as_="span"),
            " filtering, sorting, and scroll-loading via ",
            rx.code("LazyFrameGridMixin"),
            ". Multi-column filters accumulate on the backend.",
            margin_bottom="1em",
            color="var(--gray-11)",
        ),
        rx.cond(
            ParquetState.pq_loaded,
            # Data loaded -- show server-side grid
            rx.fragment(
                lazyframe_grid_stats_bar(ParquetState),
                lazyframe_grid(ParquetState, height="540px", density="compact"),
            ),
            # Not loaded yet -- show load button
            rx.box(
                rx.button(
                    "Load Parquet from HuggingFace",
                    on_click=ParquetState.load_parquet,
                    loading=ParquetState.pq_loading_init,
                    size="3",
                ),
                rx.text(
                    "Click to fetch the longevity-map weights parquet (~26 KB) "
                    "directly from HuggingFace using polars' native hf:// protocol. "
                    "Data is scanned lazily -- only page slices are collected.",
                    size="2",
                    color="var(--gray-9)",
                    margin_top="0.5em",
                ),
            ),
        ),
        lazyframe_grid_detail_box(ParquetState),
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
            on_click=GenomeState.load_genome,
            loading=GenomeState.lf_grid_loading,
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
    """The scroll-loading DataGrid for the genome, powered by GenomeState."""
    return rx.fragment(
        lazyframe_grid_stats_bar(GenomeState),
        lazyframe_grid(GenomeState),
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
            "backend -- no full-table collect for each interaction. "
            "Multi-column filters accumulate on the backend.",
            margin_bottom="1em",
            color="var(--gray-11)",
        ),
        rx.cond(
            GenomeState.genome_available,
            # File exists
            rx.cond(
                GenomeState.lf_grid_loaded,
                _genome_grid(),
                _genome_load_button(),
            ),
            # File not downloaded
            _genome_download_box(),
        ),
        lazyframe_grid_detail_box(GenomeState),
        padding_top="1em",
    )


def index() -> rx.Component:
    """Render the main page with tabs."""
    return rx.box(
        rx.heading("MUI X DataGrid -- Reflex Demo", size="6", margin_bottom="1em"),
        rx.tabs.root(
            rx.tabs.list(
                rx.tabs.trigger("PRS Results", value="prs"),
                rx.tabs.trigger("Employee Data", value="employees"),
                rx.tabs.trigger("Genomic Variants (VCF)", value="vcf"),
                rx.tabs.trigger("Longevity Map (Parquet)", value="parquet"),
                rx.tabs.trigger("Full Genome (Server-Side)", value="genome"),
            ),
            rx.tabs.content(prs_tab(), value="prs"),
            rx.tabs.content(employee_tab(), value="employees"),
            rx.tabs.content(vcf_tab(), value="vcf"),
            rx.tabs.content(parquet_tab(), value="parquet"),
            rx.tabs.content(genome_tab(), value="genome"),
            default_value="prs",
        ),
        padding="2em",
        max_width="1400px",
        margin="0 auto",
    )


app = rx.App()
app.add_page(
    index,
    on_load=[AppState.load_all, GenomeState.check_genome],
)
