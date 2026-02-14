"""CLI for reflex-mui-datagrid -- view tabular and genomic files in the browser.

Usage::

    # View a VCF file (requires [bio] extra)
    reflex-mui-datagrid view variants.vcf

    # View a CSV / TSV / Parquet file
    reflex-mui-datagrid view data.csv

    # Limit rows and set height
    reflex-mui-datagrid view big_file.parquet --limit 5000 --height 800px
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Annotated, Optional

import typer

app = typer.Typer(
    name="reflex-mui-datagrid",
    help="View tabular and genomic data files in an interactive browser grid.",
    no_args_is_help=True,
)


def _detect_format(path: Path) -> str:
    """Detect file format from extension."""
    suffix = path.suffix.lower()
    format_map: dict[str, str] = {
        ".vcf": "vcf",
        ".vcf.gz": "vcf",
        ".bcf": "vcf",
        ".csv": "csv",
        ".tsv": "tsv",
        ".parquet": "parquet",
        ".pq": "parquet",
        ".json": "json",
        ".ndjson": "ndjson",
        ".jsonl": "ndjson",
        ".ipc": "ipc",
        ".arrow": "ipc",
        ".feather": "ipc",
        ".bam": "bam",
        ".gff": "gff",
        ".gff3": "gff",
        ".gtf": "gff",
        ".bed": "bed",
        ".fasta": "fasta",
        ".fa": "fasta",
        ".fastq": "fastq",
        ".fq": "fastq",
    }
    # Check two-part extensions first (e.g. .vcf.gz)
    double_suffix = "".join(path.suffixes[-2:]).lower() if len(path.suffixes) >= 2 else ""
    if double_suffix in format_map:
        return format_map[double_suffix]
    return format_map.get(suffix, "csv")


_BIO_FORMATS: set[str] = {"vcf", "bam", "gff", "bed", "fasta", "fastq"}


def _build_app_code(
    file_path: Path,
    fmt: str,
    limit: int | None,
    height: str,
    title: str,
) -> str:
    """Generate the Reflex app module source code."""
    abs_path = str(file_path.resolve())
    # Escape backslashes and quotes for embedding in Python string literal
    safe_path = abs_path.replace("\\", "\\\\").replace('"', '\\"')

    load_code: str
    if fmt == "vcf":
        load_code = f"""
        import polars_bio as pb
        from reflex_mui_datagrid import bio_lazyframe_to_datagrid
        lf = pb.scan_vcf("{safe_path}")
        self.rows, col_defs = bio_lazyframe_to_datagrid(lf{f", limit={limit}" if limit else ""})
        self.columns = [c.dict() for c in col_defs]
        self.row_count = len(self.rows)
        self.show_descriptions = True
"""
    elif fmt in _BIO_FORMATS:
        scan_fn = f"scan_{fmt}"
        load_code = f"""
        import polars_bio as pb
        lf = pb.{scan_fn}("{safe_path}")
        from reflex_mui_datagrid import lazyframe_to_datagrid
        self.rows, col_defs = lazyframe_to_datagrid(lf{f", limit={limit}" if limit else ""})
        self.columns = [c.dict() for c in col_defs]
        self.row_count = len(self.rows)
"""
    elif fmt == "csv":
        load_code = f"""
        import polars as pl
        lf = pl.scan_csv("{safe_path}")
        from reflex_mui_datagrid import lazyframe_to_datagrid
        self.rows, col_defs = lazyframe_to_datagrid(lf{f", limit={limit}" if limit else ""})
        self.columns = [c.dict() for c in col_defs]
        self.row_count = len(self.rows)
"""
    elif fmt == "tsv":
        load_code = f"""
        import polars as pl
        lf = pl.scan_csv("{safe_path}", separator="\\t")
        from reflex_mui_datagrid import lazyframe_to_datagrid
        self.rows, col_defs = lazyframe_to_datagrid(lf{f", limit={limit}" if limit else ""})
        self.columns = [c.dict() for c in col_defs]
        self.row_count = len(self.rows)
"""
    elif fmt == "parquet":
        load_code = f"""
        import polars as pl
        lf = pl.scan_parquet("{safe_path}")
        from reflex_mui_datagrid import lazyframe_to_datagrid
        self.rows, col_defs = lazyframe_to_datagrid(lf{f", limit={limit}" if limit else ""})
        self.columns = [c.dict() for c in col_defs]
        self.row_count = len(self.rows)
"""
    elif fmt == "json":
        load_code = f"""
        import polars as pl
        df = pl.read_json("{safe_path}")
        from reflex_mui_datagrid import lazyframe_to_datagrid
        self.rows, col_defs = lazyframe_to_datagrid(df.lazy(){f", limit={limit}" if limit else ""})
        self.columns = [c.dict() for c in col_defs]
        self.row_count = len(self.rows)
"""
    elif fmt == "ndjson":
        load_code = f"""
        import polars as pl
        lf = pl.scan_ndjson("{safe_path}")
        from reflex_mui_datagrid import lazyframe_to_datagrid
        self.rows, col_defs = lazyframe_to_datagrid(lf{f", limit={limit}" if limit else ""})
        self.columns = [c.dict() for c in col_defs]
        self.row_count = len(self.rows)
"""
    elif fmt == "ipc":
        load_code = f"""
        import polars as pl
        lf = pl.scan_ipc("{safe_path}")
        from reflex_mui_datagrid import lazyframe_to_datagrid
        self.rows, col_defs = lazyframe_to_datagrid(lf{f", limit={limit}" if limit else ""})
        self.columns = [c.dict() for c in col_defs]
        self.row_count = len(self.rows)
"""
    else:
        load_code = f"""
        import polars as pl
        lf = pl.scan_csv("{safe_path}")
        from reflex_mui_datagrid import lazyframe_to_datagrid
        self.rows, col_defs = lazyframe_to_datagrid(lf{f", limit={limit}" if limit else ""})
        self.columns = [c.dict() for c in col_defs]
        self.row_count = len(self.rows)
"""

    show_desc_default = "True" if fmt == "vcf" else "False"

    # Use placeholder substitution instead of f-string to avoid escaping
    # nightmares with all the braces in the generated Python code.
    template = _APP_TEMPLATE
    template = template.replace("__FILENAME__", file_path.name)
    template = template.replace("__SHOW_DESC_DEFAULT__", show_desc_default)
    template = template.replace("__LOAD_CODE__", load_code)
    template = template.replace("__TITLE__", title)
    template = template.replace("__HEIGHT__", height)
    return template


# ---------------------------------------------------------------------------
# App template -- uses __PLACEHOLDER__ tokens for dynamic parts.
# ---------------------------------------------------------------------------

_APP_TEMPLATE = '''"""Auto-generated viewer app for: __FILENAME__"""

from typing import Any

import reflex as rx

from reflex_mui_datagrid import data_grid


# ---------------------------------------------------------------------------
# State & UI
# ---------------------------------------------------------------------------

class ViewerState(rx.State):
    rows: list[dict[str, Any]] = []
    columns: list[dict[str, Any]] = []
    row_count: int = 0
    show_descriptions: bool = __SHOW_DESC_DEFAULT__
    selected: str = "Click a row to see its details."

    def load_data(self) -> None:
__LOAD_CODE__

    def handle_row_click(self, params: dict[str, Any]) -> None:
        row: dict[str, Any] = params.get("row", {})
        if not row:
            return
        lines: list[str] = []
        for field, value in row.items():
            if field == "__row_id__":
                continue
            lines.append(f"{field}: {value}")
        self.selected = "\\n".join(lines)


def index() -> rx.Component:
    return rx.box(
        rx.heading("__TITLE__", size="6", margin_bottom="0.5em"),
        rx.text(
            ViewerState.row_count.to(str),
            " rows loaded from ",
            rx.code("__FILENAME__"),
            size="2",
            color="var(--gray-9)",
            margin_bottom="1em",
        ),
        rx.cond(
            ViewerState.rows.length() > 0,
            data_grid(
                rows=ViewerState.rows,
                columns=ViewerState.columns,
                row_id_field="__row_id__",
                show_toolbar=True,
                show_description_in_header=ViewerState.show_descriptions,
                density="compact",
                column_header_height=70,
                on_row_click=ViewerState.handle_row_click,
                height="__HEIGHT__",
                width="100%",
            ),
        ),
        rx.box(
            rx.text(
                ViewerState.selected,
                white_space="pre-wrap",
                size="2",
            ),
            margin_top="1em",
            padding="1em",
            border_radius="8px",
            background="var(--gray-a3)",
        ),
        padding="2em",
        max_width="1400px",
        margin="0 auto",
    )


app = rx.App()
app.add_page(index, on_load=ViewerState.load_data)
'''


@app.command()
def view(
    file: Annotated[Path, typer.Argument(help="Path to the data file (VCF, CSV, TSV, Parquet, JSON, etc.)")],
    limit: Annotated[Optional[int], typer.Option("--limit", "-n", help="Maximum number of rows to load")] = None,
    height: Annotated[str, typer.Option("--height", "-h", help="CSS height of the grid")] = "calc(100vh - 200px)",
    port: Annotated[int, typer.Option("--port", "-p", help="Port for the Reflex frontend")] = 3000,
    title: Annotated[Optional[str], typer.Option("--title", "-t", help="Page title")] = None,
) -> None:
    """View a data file in an interactive browser grid.

    Supports: VCF, CSV, TSV, Parquet, JSON, NDJSON, IPC/Arrow/Feather.
    Genomic formats (VCF, BAM, GFF, BED, FASTA, FASTQ) require the [bio] extra.
    """
    file = file.resolve()
    if not file.exists():
        typer.echo(f"Error: file not found: {file}", err=True)
        raise typer.Exit(code=1)

    fmt = _detect_format(file)

    if fmt in _BIO_FORMATS:
        try:
            import polars_bio  # noqa: F401
        except ImportError:
            python_hint = ""
            if sys.version_info >= (3, 14):
                python_hint = (
                    "\nDetected Python 3.14+. The [bio] extra currently requires "
                    "Python < 3.14 due to the pyarrow dependency chain.\n"
                    "Try: uv tool install --python 3.13 \"reflex-mui-datagrid[bio]\""
                )
            typer.echo(
                f"Error: viewing {fmt.upper()} files requires the [bio] extra.\n"
                f"Install it with: uv add \"reflex-mui-datagrid[bio]\""
                f"{python_hint}",
                err=True,
            )
            raise typer.Exit(code=1)

    if title is None:
        title = f"{file.name} — DataGrid Viewer"

    app_code = _build_app_code(file, fmt, limit, height, title)

    # Create a temporary Reflex app directory.
    tmp_dir = Path(tempfile.mkdtemp(prefix="datagrid_viewer_"))
    app_name = "viewer_app"
    app_pkg = tmp_dir / app_name
    app_pkg.mkdir()
    (app_pkg / "__init__.py").write_text("")
    (app_pkg / f"{app_name}.py").write_text(app_code)

    rxconfig_code = f"""import reflex as rx
config = rx.Config(app_name="{app_name}", frontend_port={port})
"""
    (tmp_dir / "rxconfig.py").write_text(rxconfig_code)

    typer.echo(f"Launching viewer for: {file}")
    typer.echo(f"Format: {fmt} | Limit: {limit or 'all'} | Port: {port}")

    os.chdir(tmp_dir)

    # Step 1: initialise the Reflex project (creates .web/ with node_modules).
    # We use subprocess because reflex's CLI calls sys.exit() on completion.
    typer.echo("Initializing Reflex project...")
    subprocess.run(
        [sys.executable, "-m", "reflex", "init"],
        cwd=str(tmp_dir),
        check=True,
    )

    # Step 2: run the app via exec (replaces this process).
    typer.echo("Starting viewer...")
    os.execvp(sys.executable, [sys.executable, "-m", "reflex", "run"])


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
