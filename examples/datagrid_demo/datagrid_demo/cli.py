"""CLI for the DataGrid demo app.

Commands::

    uv run demo                  # Run the Reflex demo app
    uv run demo run              # Same as above
    uv run demo download-genome  # Download full genome VCF from Zenodo (~483 MB)
"""

import json
import os
import urllib.request
from pathlib import Path

import typer

app = typer.Typer(
    name="demo",
    help="DataGrid demo app with genome viewer.",
    invoke_without_command=True,
)

GENOME_URL: str = "https://zenodo.org/records/18370498/files/antonkulaga.vcf?download=1"
DATA_DIR: Path = Path(__file__).resolve().parent / "data"
GENOME_PATH: Path = DATA_DIR / "antonkulaga.vcf"
# JSON sidecar for HTTP caching metadata (ETag, size).
GENOME_META_PATH: Path = DATA_DIR / ".antonkulaga.vcf.meta.json"


def _run_app() -> None:
    """Start the Reflex demo app."""
    app_dir = Path(__file__).resolve().parent.parent
    os.chdir(app_dir)

    from reflex.reflex import cli

    cli(["run"])


@app.callback(invoke_without_command=True)
def default(ctx: typer.Context) -> None:
    """Run the demo app (default when no subcommand is given)."""
    if ctx.invoked_subcommand is None:
        _run_app()


@app.command()
def run() -> None:
    """Run the Reflex demo app."""
    _run_app()


def _read_cache_meta() -> dict[str, str]:
    """Read cached HTTP metadata (ETag, Content-Length) from the sidecar JSON."""
    if GENOME_META_PATH.exists():
        return json.loads(GENOME_META_PATH.read_text())
    return {}


def _write_cache_meta(meta: dict[str, str]) -> None:
    """Persist HTTP metadata to the sidecar JSON."""
    GENOME_META_PATH.write_text(json.dumps(meta, indent=2))


def _is_cache_fresh() -> bool:
    """Check if the cached genome file is still fresh using a HEAD request + ETag.

    Returns True if the file exists and the server's ETag matches the
    cached one (or if the server is unreachable — assume cache is valid).
    """
    if not GENOME_PATH.exists():
        return False

    meta = _read_cache_meta()
    cached_etag = meta.get("etag")
    if not cached_etag:
        # No ETag stored — trust the file if it has non-zero size.
        return GENOME_PATH.stat().st_size > 0

    req = urllib.request.Request(GENOME_URL, method="HEAD")
    resp = urllib.request.urlopen(req, timeout=15)
    server_etag = resp.headers.get("ETag", "")
    return server_etag == cached_etag


def _download_with_resume(dest: Path, part: Path) -> None:
    """Download the genome VCF, resuming a partial download if possible.

    Uses ``Range`` header so that a previously interrupted download can
    pick up where it left off instead of re-downloading from scratch.
    Stores ETag in a sidecar JSON for future freshness checks.
    """
    existing_bytes = part.stat().st_size if part.exists() else 0

    headers: dict[str, str] = {}
    if existing_bytes > 0:
        headers["Range"] = f"bytes={existing_bytes}-"
        typer.echo(f"  Resuming from {existing_bytes / (1024 * 1024):.1f} MB")

    req = urllib.request.Request(GENOME_URL, headers=headers)
    resp = urllib.request.urlopen(req, timeout=30)

    # If server doesn't support Range (200 instead of 206), start fresh.
    if resp.status == 200 and existing_bytes > 0:
        typer.echo("  Server does not support resume — downloading from scratch.")
        existing_bytes = 0

    content_length = resp.headers.get("Content-Length")
    total_size = int(content_length) + existing_bytes if content_length else -1

    mode = "ab" if (existing_bytes > 0 and resp.status == 206) else "wb"
    if mode == "wb":
        existing_bytes = 0  # reset counter for progress display

    chunk_size = 1024 * 256  # 256 KB
    downloaded = existing_bytes

    with part.open(mode) as f:
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                pct = min(100.0, downloaded * 100.0 / total_size)
                mb_done = downloaded / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)
                typer.echo(
                    f"\r  {mb_done:.1f} / {mb_total:.1f} MB ({pct:.1f}%)", nl=False
                )
            else:
                mb_done = downloaded / (1024 * 1024)
                typer.echo(f"\r  {mb_done:.1f} MB downloaded", nl=False)

    typer.echo()  # newline after progress

    part.rename(dest)

    # Persist ETag for future cache checks.
    etag = resp.headers.get("ETag", "")
    _write_cache_meta({"etag": etag, "size": str(dest.stat().st_size)})


@app.command()
def download_genome() -> None:
    """Download the full human genome VCF from Zenodo (~483 MB).

    Source: https://zenodo.org/records/18370498
    The file is saved to the demo's data/ directory.

    Features:
    - Caches the file on disk and checks the server ETag before re-downloading.
    - Supports resuming interrupted downloads via HTTP Range requests.
    """
    if GENOME_PATH.exists():
        size_mb = GENOME_PATH.stat().st_size / (1024 * 1024)
        typer.echo(f"Genome file already exists: {GENOME_PATH} ({size_mb:.1f} MB)")

        # Check freshness via ETag.
        typer.echo("  Checking if remote file has changed...")
        if _is_cache_fresh():
            typer.echo("  File is up to date (ETag matches). Nothing to download.")
            raise typer.Exit()
        else:
            typer.echo("  Remote file may have changed.")
            overwrite = typer.confirm("Download again?", default=False)
            if not overwrite:
                raise typer.Exit()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    part_path = GENOME_PATH.with_suffix(".vcf.part")

    typer.echo("Downloading genome VCF from Zenodo...")
    typer.echo(f"  URL:  {GENOME_URL}")
    typer.echo(f"  Dest: {GENOME_PATH}")
    typer.echo()

    _download_with_resume(GENOME_PATH, part_path)

    size_mb = GENOME_PATH.stat().st_size / (1024 * 1024)
    typer.echo(f"Download complete: {size_mb:.1f} MB")
    typer.echo("Run the demo with: uv run demo")


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
