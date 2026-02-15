"""CLI for reflex-mui-datagrid -- view tabular and genomic files in the browser.

Usage::

    # View a VCF file (requires [bio] extra)
    reflex-mui-datagrid view variants.vcf

    # View a CSV / TSV / Parquet file
    reflex-mui-datagrid view data.csv

    # Limit rows and set height
    reflex-mui-datagrid view big_file.parquet --limit 5000 --height 800px

All file formats use the reusable ``LazyFrameGridMixin`` for server-side
scroll-loading, filtering, and sorting.
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
    """Generate the Reflex app module source code.

    Uses ``scan_file`` + ``LazyFrameGridMixin`` + ``lazyframe_grid`` for
    server-side scroll-loading of all file formats.
    """
    abs_path = str(file_path.resolve())
    # Escape backslashes and quotes for embedding in Python string literal
    safe_path = abs_path.replace("\\", "\\\\").replace('"', '\\"')

    limit_kwarg = f", chunk_size={limit}" if limit else ""

    # Use placeholder substitution to avoid escaping nightmares.
    template = _APP_TEMPLATE
    template = template.replace("__FILENAME__", file_path.name)
    template = template.replace("__SAFE_PATH__", safe_path)
    template = template.replace("__LIMIT_KWARG__", limit_kwarg)
    template = template.replace("__TITLE__", title)
    template = template.replace("__HEIGHT__", height)
    return template


# ---------------------------------------------------------------------------
# App template -- uses __PLACEHOLDER__ tokens for dynamic parts.
# ---------------------------------------------------------------------------

_APP_TEMPLATE = '''"""Auto-generated viewer app for: __FILENAME__"""

from pathlib import Path
from typing import Any

import reflex as rx

from reflex_mui_datagrid import (
    LazyFrameGridMixin,
    lazyframe_grid,
    lazyframe_grid_detail_box,
    lazyframe_grid_stats_bar,
    scan_file,
)


class ViewerState(LazyFrameGridMixin):
    """Viewer state using LazyFrameGridMixin for server-side browsing."""

    def load_data(self):
        lf, descriptions = scan_file(Path("__SAFE_PATH__"))
        yield from self.set_lazyframe(lf, descriptions__LIMIT_KWARG__)


def index() -> rx.Component:
    return rx.box(
        rx.heading("__TITLE__", size="6", margin_bottom="0.5em"),
        rx.cond(
            ViewerState.lf_grid_loaded,
            rx.fragment(
                lazyframe_grid_stats_bar(ViewerState),
                lazyframe_grid(ViewerState, height="__HEIGHT__"),
            ),
            rx.text("Loading...", color="var(--gray-9)"),
        ),
        lazyframe_grid_detail_box(ViewerState),
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

    All formats use server-side scroll-loading with filtering and sorting.
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
            typer.echo(
                f"Error: viewing {fmt.upper()} files requires the [bio] extra.\n"
                f"Install it with: uv add \"reflex-mui-datagrid[bio]\"",
                err=True,
            )
            raise typer.Exit(code=1)

    if title is None:
        title = f"{file.name} -- DataGrid Viewer"

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
