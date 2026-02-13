"""CLI entrypoint for the DataGrid demo app.

Allows running the demo from the workspace root via:
    uv run demo
"""

import os
from pathlib import Path


def main() -> None:
    """Run the Reflex demo app."""
    # Reflex expects rxconfig.py in the cwd
    app_dir = Path(__file__).resolve().parent.parent
    os.chdir(app_dir)

    from reflex.reflex import cli

    cli(["run"])
