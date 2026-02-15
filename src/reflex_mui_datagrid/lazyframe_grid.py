"""Reusable server-side LazyFrame grid: mixin, file scanner, and UI helper.

This module provides a complete server-side scroll-loading DataGrid
experience backed by a polars LazyFrame.  Users inherit from
:class:`LazyFrameGridMixin` (which extends ``rx.State``), call
:meth:`set_lazyframe` with any LazyFrame, and render with
:func:`lazyframe_grid`.

Typical usage::

    from reflex_mui_datagrid import LazyFrameGridMixin, lazyframe_grid, scan_file

    class MyState(LazyFrameGridMixin):
        def load_data(self):
            lf, descriptions = scan_file(Path("my_genome.vcf"))
            yield from self.set_lazyframe(lf, descriptions)

    def index():
        return rx.cond(MyState.lf_grid_loaded, lazyframe_grid(MyState))
"""

import time
from pathlib import Path
from typing import Any

import polars as pl
import reflex as rx

from reflex_mui_datagrid.datagrid import data_grid
from reflex_mui_datagrid.polars_utils import (
    _dataframe_to_dicts,
    apply_filter_model,
    apply_sort_model,
    build_column_defs_from_schema,
)


# ---------------------------------------------------------------------------
# Module-level LazyFrame cache
# ---------------------------------------------------------------------------

_DEFAULT_CHUNK_SIZE: int = 200
_DEFAULT_VALUE_OPTIONS_SAMPLE_ROWS: int = 20_000
_DEFAULT_VALUE_OPTIONS_MAX_UNIQUE: int = 50


class _LazyFrameCache:
    """Holds a LazyFrame and its derived metadata outside Reflex state.

    LazyFrames are not JSON-serialisable, so they cannot live inside
    ``rx.State``.  This cache stores them in a module-level registry
    keyed by a string ID (typically the state class name).
    """

    def __init__(self) -> None:
        self.lf: pl.LazyFrame | None = None
        self.schema: pl.Schema | None = None
        self.descriptions: dict[str, str] = {}
        self.col_defs: list[dict[str, Any]] = []
        self.total_rows: int = 0


_cache_registry: dict[str, _LazyFrameCache] = {}


def _get_cache(cache_id: str) -> _LazyFrameCache:
    """Return (or create) the cache entry for *cache_id*."""
    if cache_id not in _cache_registry:
        _cache_registry[cache_id] = _LazyFrameCache()
    return _cache_registry[cache_id]


# ---------------------------------------------------------------------------
# File scanner
# ---------------------------------------------------------------------------

def scan_file(path: Path) -> tuple[pl.LazyFrame, dict[str, str]]:
    """Scan a data file and return a ``(LazyFrame, descriptions)`` tuple.

    Auto-detects the file format from the extension:

    * ``.vcf`` / ``.vcf.gz`` / ``.bcf`` -- uses ``polars_bio.scan_vcf()``
      and auto-extracts column descriptions from the VCF header.
    * ``.parquet`` / ``.pq`` -- uses ``pl.scan_parquet()``.
    * ``.csv`` -- uses ``pl.scan_csv()``.
    * ``.tsv`` -- uses ``pl.scan_csv(separator="\\t")``.
    * ``.json`` -- uses ``pl.read_json().lazy()`` (no streaming scan).
    * ``.ndjson`` / ``.jsonl`` -- uses ``pl.scan_ndjson()``.
    * ``.ipc`` / ``.arrow`` / ``.feather`` -- uses ``pl.scan_ipc()``.

    Args:
        path: Path to the data file.

    Returns:
        A ``(lazyframe, descriptions)`` tuple.  For VCF files the
        descriptions dict is populated from the file header; for other
        formats it is empty.

    Raises:
        FileNotFoundError: If *path* does not exist.
        ImportError: If a VCF file is given but ``polars-bio`` is not
            installed.
        ValueError: If the file extension is not recognised.
    """
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    suffix = path.suffix.lower()
    # Handle two-part extensions like .vcf.gz
    double_suffix = "".join(path.suffixes[-2:]).lower() if len(path.suffixes) >= 2 else ""

    descriptions: dict[str, str] = {}

    # VCF / BCF
    if suffix in (".vcf", ".bcf") or double_suffix == ".vcf.gz":
        import polars_bio as pb

        from reflex_mui_datagrid.polars_bio_utils import extract_vcf_descriptions

        lf = pb.scan_vcf(str(path))
        descriptions = extract_vcf_descriptions(lf)
        return lf, descriptions

    # Parquet
    if suffix in (".parquet", ".pq"):
        return pl.scan_parquet(path), descriptions

    # CSV
    if suffix == ".csv":
        return pl.scan_csv(path), descriptions

    # TSV
    if suffix == ".tsv":
        return pl.scan_csv(path, separator="\t"), descriptions

    # JSON (no streaming scan -- read then convert to lazy)
    if suffix == ".json":
        return pl.read_json(path).lazy(), descriptions

    # NDJSON / JSONL
    if suffix in (".ndjson", ".jsonl"):
        return pl.scan_ndjson(path), descriptions

    # IPC / Arrow / Feather
    if suffix in (".ipc", ".arrow", ".feather"):
        return pl.scan_ipc(path), descriptions

    raise ValueError(
        f"Unsupported file extension: {suffix!r}. "
        "Supported: .vcf, .vcf.gz, .bcf, .parquet, .pq, .csv, .tsv, "
        ".json, .ndjson, .jsonl, .ipc, .arrow, .feather"
    )


# ---------------------------------------------------------------------------
# Value-options inference
# ---------------------------------------------------------------------------

def _infer_value_options_from_sample(
    lf: pl.LazyFrame,
    schema: pl.Schema,
    *,
    sample_rows: int = _DEFAULT_VALUE_OPTIONS_SAMPLE_ROWS,
    max_unique: int = _DEFAULT_VALUE_OPTIONS_MAX_UNIQUE,
) -> dict[str, list[str]]:
    """Infer low-cardinality value options from a bounded sample.

    Avoids expensive full-file ``n_unique`` scans.  The options are used
    only for UI filter dropdowns, so sampled values are sufficient.
    """
    sample_df = lf.head(sample_rows).collect()

    value_options: dict[str, list[str]] = {}
    for col_name in sample_df.columns:
        unique_values = sample_df[col_name].drop_nulls().unique().to_list()
        if 0 < len(unique_values) <= max_unique:
            values = sorted(str(v) for v in unique_values)
            value_options[col_name] = values

    return value_options


# ---------------------------------------------------------------------------
# LazyFrameGridMixin
# ---------------------------------------------------------------------------

class LazyFrameGridMixin(rx.State):
    """Reflex State mixin for server-side scroll-loading DataGrids.

    Inherit from this class to get a complete set of state variables
    and event handlers for server-side filtering, sorting, and
    infinite-scroll loading backed by a polars LazyFrame.

    This class extends ``rx.State`` so that Reflex's metaclass
    properly registers all state vars as reactive variables.

    All state variable names are prefixed with ``lf_grid_`` to avoid
    collisions when composed with other state.

    Example::

        class MyState(LazyFrameGridMixin):
            def load_data(self):
                lf, descriptions = scan_file(Path("data.parquet"))
                yield from self.set_lazyframe(lf, descriptions)
    """

    # -- Frontend state vars --
    lf_grid_rows: list[dict[str, Any]] = []
    lf_grid_columns: list[dict[str, Any]] = []
    lf_grid_row_count: int = 0
    lf_grid_loading: bool = False
    lf_grid_loaded: bool = False
    lf_grid_stats: str = ""
    lf_grid_selected_info: str = "Click a row to see details."
    lf_grid_pagination_model: dict[str, int] = {
        "page": 0,
        "pageSize": _DEFAULT_CHUNK_SIZE,
    }

    # -- Backend-only vars (not sent to frontend) --
    _lf_grid_filter: dict[str, Any] = {}
    _lf_grid_sort: list[dict[str, Any]] = []
    _lf_grid_cache_id: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_lazyframe(
        self,
        lf: pl.LazyFrame,
        descriptions: dict[str, str] | None = None,
        *,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
        value_options_sample_rows: int = _DEFAULT_VALUE_OPTIONS_SAMPLE_ROWS,
        value_options_max_unique: int = _DEFAULT_VALUE_OPTIONS_MAX_UNIQUE,
    ):
        """Prepare a LazyFrame for server-side browsing.

        This is a **generator** -- use ``yield from self.set_lazyframe(...)``
        inside your event handler so the loading state is sent to the
        frontend immediately.

        The LazyFrame is stored in a module-level cache (never serialised
        into Reflex state).  Only the schema, total row count, and
        low-cardinality value options are computed up-front.

        Args:
            lf: The polars LazyFrame to browse.
            descriptions: Optional ``{column: description}`` mapping for
                column header tooltips / subtitles.
            chunk_size: Number of rows to load per scroll chunk.
            value_options_sample_rows: How many rows to sample for
                inferring dropdown filter options.
            value_options_max_unique: Maximum distinct values for a
                column to qualify for a dropdown filter.
        """
        self.lf_grid_loading = True  # type: ignore[assignment]
        self.lf_grid_selected_info = "Preparing LazyFrame..."  # type: ignore[assignment]
        yield  # send loading state to the frontend immediately

        # Determine cache ID from the state class name.
        cache_id = type(self).__name__
        self._lf_grid_cache_id = cache_id  # type: ignore[assignment]
        cache = _get_cache(cache_id)

        cache.lf = lf
        cache.descriptions = descriptions or {}
        cache.schema = lf.collect_schema()

        # Count total rows (Polars can push this into the scan).
        cache.total_rows = lf.select(pl.len()).collect().item()

        # Detect low-cardinality columns from a bounded sample.
        value_options = _infer_value_options_from_sample(
            lf,
            cache.schema,
            sample_rows=value_options_sample_rows,
            max_unique=value_options_max_unique,
        )

        col_defs = build_column_defs_from_schema(
            cache.schema,
            value_options_map=value_options,
            column_descriptions=cache.descriptions,
        )
        cache.col_defs = [c.dict() for c in col_defs]

        self.lf_grid_columns = cache.col_defs  # type: ignore[assignment]
        self.lf_grid_loaded = True  # type: ignore[assignment]
        self._lf_grid_filter = {}  # type: ignore[assignment]
        self._lf_grid_sort = []  # type: ignore[assignment]
        self.lf_grid_pagination_model = {  # type: ignore[assignment]
            "page": 0,
            "pageSize": chunk_size,
        }
        self._refresh_lf_grid_page(append=False, refresh_row_count=True)
        self.lf_grid_loading = False  # type: ignore[assignment]
        self.lf_grid_selected_info = (  # type: ignore[assignment]
            f"Ready: {cache.total_rows:,} rows. Scroll down to load more."
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def handle_lf_grid_filter(self, filter_model: dict[str, Any]) -> None:
        """Handle server-side filter change -- reset scroll stream to top."""
        self._lf_grid_filter = filter_model  # type: ignore[assignment]
        page_size = self.lf_grid_pagination_model.get("pageSize", _DEFAULT_CHUNK_SIZE)
        self.lf_grid_pagination_model = {"page": 0, "pageSize": page_size}  # type: ignore[assignment]
        self._refresh_lf_grid_page(append=False, refresh_row_count=True)

    def handle_lf_grid_sort(self, sort_model: list[dict[str, Any]]) -> None:
        """Handle server-side sort change -- reset scroll stream to top."""
        self._lf_grid_sort = sort_model  # type: ignore[assignment]
        page_size = self.lf_grid_pagination_model.get("pageSize", _DEFAULT_CHUNK_SIZE)
        self.lf_grid_pagination_model = {"page": 0, "pageSize": page_size}  # type: ignore[assignment]
        self._refresh_lf_grid_page(append=False, refresh_row_count=True)

    def handle_lf_grid_scroll_end(self, _params: dict[str, Any]) -> None:
        """Load the next chunk when the virtual scroller nears the bottom."""
        if self.lf_grid_loading:
            return

        page = self.lf_grid_pagination_model.get("page", 0)
        page_size = self.lf_grid_pagination_model.get("pageSize", _DEFAULT_CHUNK_SIZE)
        next_offset = (page + 1) * page_size
        if next_offset >= self.lf_grid_row_count:
            return

        t0 = time.perf_counter()
        self.lf_grid_pagination_model = {"page": page + 1, "pageSize": page_size}  # type: ignore[assignment]
        self._refresh_lf_grid_page(append=True, refresh_row_count=False)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        total_rows = len(self.lf_grid_rows)
        print(
            f"[LazyFrameGrid] scroll-end chunk: "
            f"page={page + 1}, offset={next_offset}, "
            f"+{page_size} rows, total={total_rows}, "
            f"elapsed={elapsed_ms:.1f}ms"
        )

    def handle_lf_grid_row_click(self, params: dict[str, Any]) -> None:
        """Handle row click -- show all fields with descriptions."""
        row: dict[str, Any] = params.get("row", {})
        if not row:
            return

        cache_id = self._lf_grid_cache_id
        descs = _get_cache(cache_id).descriptions if cache_id else {}

        lines: list[str] = []
        for field, value in row.items():
            if field == "__row_id__":
                continue
            desc = descs.get(field, "")
            if desc:
                lines.append(f"{field}: {value}  ({desc})")
            else:
                lines.append(f"{field}: {value}")
        self.lf_grid_selected_info = "\n".join(lines)  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refresh_lf_grid_page(
        self,
        *,
        append: bool,
        refresh_row_count: bool,
    ) -> None:
        """Collect only the current page from the cached LazyFrame.

        Builds a lazy query: filter -> count -> sort -> slice, then
        collects only the small page slice.
        """
        cache_id = self._lf_grid_cache_id
        if not cache_id:
            return
        cache = _get_cache(cache_id)
        if cache.lf is None:
            return

        t0 = time.perf_counter()
        lf: pl.LazyFrame = cache.lf

        # Apply filter.
        if self._lf_grid_filter and self._lf_grid_filter.get("items"):
            lf = apply_filter_model(lf, self._lf_grid_filter, cache.schema)

        # Count filtered rows when the stream is reset.
        if refresh_row_count:
            t_count = time.perf_counter()
            self.lf_grid_row_count = lf.select(pl.len()).collect().item()  # type: ignore[assignment]
            print(
                f"[LazyFrameGrid] row count: {self.lf_grid_row_count:,} "
                f"({(time.perf_counter() - t_count) * 1000:.1f}ms)"
            )

        # Apply sort.
        if self._lf_grid_sort:
            lf = apply_sort_model(lf, self._lf_grid_sort)

        # Slice to current page -- only this slice is collected.
        page = self.lf_grid_pagination_model.get("page", 0)
        page_size = self.lf_grid_pagination_model.get("pageSize", _DEFAULT_CHUNK_SIZE)
        offset = page * page_size
        page_df: pl.DataFrame = lf.slice(offset, page_size).collect()

        # Add stable row IDs (global index within the filtered+sorted result).
        page_df = page_df.with_row_index("__row_id__", offset=offset)

        # Convert to JSON-safe dicts.
        rows = _dataframe_to_dicts(page_df)
        if append:
            self.lf_grid_rows = self.lf_grid_rows + rows  # type: ignore[assignment]
        else:
            self.lf_grid_rows = rows  # type: ignore[assignment]

        elapsed_ms = (time.perf_counter() - t0) * 1000
        total_loaded = len(self.lf_grid_rows)
        mode = "append" if append else "replace"
        self.lf_grid_stats = (  # type: ignore[assignment]
            f"offset={offset:,}  +{len(rows)} rows  "
            f"loaded={total_loaded:,} / {self.lf_grid_row_count:,}  "
            f"{elapsed_ms:.0f}ms  ({mode})"
        )
        print(
            f"[LazyFrameGrid] page refresh: offset={offset}, "
            f"slice={len(rows)}, mode={mode}, "
            f"elapsed={elapsed_ms:.1f}ms"
        )


# ---------------------------------------------------------------------------
# UI helper
# ---------------------------------------------------------------------------

def lazyframe_grid(
    state_cls: type,
    *,
    height: str = "600px",
    width: str = "100%",
    density: str = "compact",
    column_header_height: int = 70,
    scroll_end_threshold: int = 260,
    show_toolbar: bool = True,
    show_description_in_header: bool = True,
    debug_log: bool = True,
    on_row_click: Any = None,
    **extra_props: Any,
) -> rx.Component:
    """Return a pre-wired ``data_grid(...)`` bound to a :class:`LazyFrameGridMixin` state.

    This creates a DataGrid component with server-side filtering,
    sorting, and scroll-loading already connected to the mixin's
    event handlers and state variables.

    Args:
        state_cls: The ``rx.State`` subclass that also inherits from
            :class:`LazyFrameGridMixin`.
        height: CSS height of the grid container.
        width: CSS width of the grid container.
        density: Grid density (``"comfortable"``, ``"compact"``, ``"standard"``).
        column_header_height: Header height in pixels.
        scroll_end_threshold: Pixel distance from bottom to trigger
            the next chunk load.
        show_toolbar: Show the MUI toolbar.
        show_description_in_header: Show column descriptions as subtitles.
        debug_log: Enable browser console debug logging.
        on_row_click: Override the default row-click handler.  If ``None``,
            uses the mixin's ``handle_lf_grid_row_click``.
        **extra_props: Additional props forwarded to ``data_grid()``.

    Returns:
        A ``data_grid(...)`` Reflex component.
    """
    if on_row_click is None:
        on_row_click = state_cls.handle_lf_grid_row_click

    return data_grid(
        rows=state_cls.lf_grid_rows,
        columns=state_cls.lf_grid_columns,
        row_id_field="__row_id__",
        # -- Scroll-loading mode --
        pagination=False,
        hide_footer=True,
        filter_mode="server",
        sorting_mode="server",
        # -- Display --
        loading=state_cls.lf_grid_loading,
        show_toolbar=show_toolbar,
        show_description_in_header=show_description_in_header,
        density=density,
        column_header_height=column_header_height,
        scroll_end_threshold=scroll_end_threshold,
        debug_log=debug_log,
        # -- Events --
        on_rows_scroll_end=state_cls.handle_lf_grid_scroll_end,
        on_filter_model_change=state_cls.handle_lf_grid_filter,
        on_sort_model_change=state_cls.handle_lf_grid_sort,
        on_row_click=on_row_click,
        height=height,
        width=width,
        **extra_props,
    )


def lazyframe_grid_stats_bar(state_cls: type) -> rx.Component:
    """Return a stats bar component showing live refresh metrics.

    Displays the filtered row count and the last refresh timing info.
    Pair with :func:`lazyframe_grid` for a complete UI.

    Args:
        state_cls: The ``rx.State`` subclass that inherits from
            :class:`LazyFrameGridMixin`.

    Returns:
        A Reflex component.
    """
    return rx.cond(
        state_cls.lf_grid_stats != "",
        rx.box(
            rx.hstack(
                rx.text(
                    state_cls.lf_grid_row_count.to(str),  # type: ignore[union-attr]
                    " rows (filtered)",
                    size="2",
                    weight="medium",
                ),
                rx.text("|", size="2", color="var(--gray-7)"),
                rx.text(
                    state_cls.lf_grid_stats,
                    size="1",
                    color="var(--gray-9)",
                    font_family="monospace",
                ),
                spacing="2",
                align="center",
            ),
            padding="0.4em 0.8em",
            border_radius="6px",
            background="var(--blue-a2)",
            border="1px solid var(--blue-a5)",
            margin_bottom="0.5em",
        ),
        rx.text(
            state_cls.lf_grid_row_count.to(str),  # type: ignore[union-attr]
            " rows (filtered)",
            size="2",
            color="var(--gray-9)",
            margin_bottom="0.5em",
        ),
    )


def lazyframe_grid_detail_box(state_cls: type) -> rx.Component:
    """Return a detail box showing the selected row's fields.

    Args:
        state_cls: The ``rx.State`` subclass that inherits from
            :class:`LazyFrameGridMixin`.

    Returns:
        A Reflex component.
    """
    return rx.box(
        rx.text(
            state_cls.lf_grid_selected_info,
            white_space="pre-wrap",
            size="2",
        ),
        margin_top="1em",
        padding="1em",
        border_radius="8px",
        background="var(--gray-a3)",
    )
