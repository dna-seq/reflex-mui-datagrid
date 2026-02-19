"""Reusable server-side LazyFrame grid: mixin, file scanner, and UI helper.

This module provides a complete server-side scroll-loading DataGrid
experience backed by a polars LazyFrame.  Users inherit from
:class:`LazyFrameGridMixin` **and** ``rx.State``, call
:meth:`set_lazyframe` with any LazyFrame, and render with
:func:`lazyframe_grid`.

``LazyFrameGridMixin`` is a Reflex **state mixin** (``mixin=True``).
Each subclass gets its own independent set of ``lf_grid_*`` reactive
variables, so multiple grids on the same page do not interfere with
each other.

All operations are truly lazy -- the full dataset is **never**
collected into memory.  Row counts use streaming counts, value
options for filter dropdowns use a hybrid strategy (eagerly
computed at init for small datasets, on-demand for large ones),
and only small page slices are ever materialised.

Typical usage::

    from reflex_mui_datagrid import LazyFrameGridMixin, lazyframe_grid, scan_file

    class MyState(LazyFrameGridMixin, rx.State):
        def load_data(self):
            lf, descriptions = scan_file(Path("my_genome.vcf"))
            yield from self.set_lazyframe(lf, descriptions)

    def index():
        return rx.cond(MyState.lf_grid_loaded, lazyframe_grid(MyState))
"""

import json
import time
from pathlib import Path
from typing import Any

import polars as pl
import reflex as rx

from reflex_mui_datagrid.datagrid import data_grid
from reflex_mui_datagrid.polars_utils import (
    _dataframe_to_dicts,
    _resolve_field_name,
    apply_filter_model,
    apply_sort_model,
    build_column_defs_from_schema,
)


# ---------------------------------------------------------------------------
# Module-level LazyFrame cache
# ---------------------------------------------------------------------------

_DEFAULT_CHUNK_SIZE: int = 200
_DEFAULT_VALUE_OPTIONS_MAX_UNIQUE: int = 500
_DEFAULT_EAGER_VALUE_OPTIONS_ROW_LIMIT: int = 50_000


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
        self.value_options_max_unique: int = _DEFAULT_VALUE_OPTIONS_MAX_UNIQUE
        # Lazily computed per-column value options.
        # None means "not yet computed"; empty list means "computed, too many".
        self._value_options_cache: dict[str, list[str] | None] = {}


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
# Lazy per-column value-options inference
# ---------------------------------------------------------------------------

def _infer_value_options_for_column(
    lf: pl.LazyFrame,
    col_name: str,
    *,
    max_unique: int = _DEFAULT_VALUE_OPTIONS_MAX_UNIQUE,
) -> list[str] | None:
    """Query the LazyFrame for distinct values of a single column.

    Only scans the single column (projection pushdown), and stops after
    ``max_unique + 1`` unique values.  Returns ``None`` if the column
    exceeds the threshold (falls back to free-text filter).

    This is called lazily -- only when the user first interacts with a
    column's filter -- so init never pays the cost of scanning all
    string columns upfront.
    """
    cap = max_unique + 1
    result = (
        lf.select(pl.col(col_name).cast(pl.String).drop_nulls().unique().head(cap))
        .collect()
    )
    values = result[col_name].drop_nulls().to_list()
    if 0 < len(values) <= max_unique:
        return sorted(str(v) for v in values)
    return None


def _get_or_compute_value_options(
    cache: _LazyFrameCache,
    col_name: str,
) -> list[str] | None:
    """Return cached value options for *col_name*, computing on first access.

    Returns the sorted list of distinct values if the column qualifies
    for a ``singleSelect`` dropdown, or ``None`` if it exceeds the
    threshold.  Results are cached so subsequent calls are free.
    """
    if col_name in cache._value_options_cache:
        return cache._value_options_cache[col_name]

    if cache.lf is None or cache.schema is None:
        return None

    dtype = cache.schema.get(col_name)
    if dtype is None:
        return None

    # Only compute for string-like columns.
    if not isinstance(dtype, (pl.String, pl.Categorical, pl.Enum)):
        cache._value_options_cache[col_name] = None
        return None

    t0 = time.perf_counter()
    options = _infer_value_options_for_column(
        cache.lf,
        col_name,
        max_unique=cache.value_options_max_unique,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000
    cache._value_options_cache[col_name] = options
    n = len(options) if options else 0
    print(
        f"[LazyFrameGrid] value options for '{col_name}': "
        f"{n} values ({elapsed_ms:.1f}ms)"
    )
    return options


# ---------------------------------------------------------------------------
# LazyFrameGridMixin
# ---------------------------------------------------------------------------

class LazyFrameGridMixin(rx.State, mixin=True):
    """Reflex State mixin for server-side scroll-loading DataGrids.

    Inherit from this class **and** ``rx.State`` to get a complete set
    of state variables and event handlers for server-side filtering,
    sorting, and infinite-scroll loading backed by a polars LazyFrame.

    This is a Reflex **mixin** (``mixin=True``).  The state vars
    declared here are *not* registered on the mixin itself -- they are
    injected into each concrete subclass by Reflex's metaclass.  This
    means every subclass gets its own independent set of ``lf_grid_*``
    reactive variables, so multiple grids on the same page do not
    interfere with each other.

    .. important::

       Subclasses **must** also inherit from ``rx.State`` (or another
       non-mixin state class) so that Reflex's metaclass registers the
       vars on the child::

           class MyGrid(LazyFrameGridMixin, rx.State):
               ...

    All operations are truly lazy:

    * **Row count** is computed via a single ``select(pl.len())``
      pushed down into the scan engine (no full materialisation).
    * **Value options** for filter dropdowns use a hybrid strategy:
      eagerly computed at init for small datasets (row count <=
      ``eager_value_options_row_limit``), deferred and computed
      on-demand (filter icon click) for large datasets.
    * **Page slices** collect only the requested chunk.

    All state variable names are prefixed with ``lf_grid_`` to avoid
    collisions when composed with other state.

    Example::

        class MyState(LazyFrameGridMixin, rx.State):
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
    lf_grid_filter_debug: str = "No active filters or sorts."
    lf_grid_filter_preset_json: str = ""
    lf_grid_debug_expanded: bool = False
    lf_grid_filter_model: dict[str, Any] = {"items": []}
    lf_grid_active_filter_fields: list[str] = []
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
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
        value_options_max_unique: int = _DEFAULT_VALUE_OPTIONS_MAX_UNIQUE,
        eager_value_options_row_limit: int = _DEFAULT_EAGER_VALUE_OPTIONS_ROW_LIMIT,
    ):
        """Prepare a LazyFrame for server-side browsing.

        This is a **generator** -- use ``yield from self.set_lazyframe(...)``
        inside your event handler so the loading state is sent to the
        frontend immediately.

        The LazyFrame is stored in a module-level cache (never serialised
        into Reflex state).  Only the schema and first page slice are
        computed at init time.  Row count is obtained via a lightweight
        ``select(pl.len())`` query (pushed down by Polars).

        Value options for filter dropdowns use a **hybrid** strategy:

        * For datasets with <= *eager_value_options_row_limit* rows,
          value options are computed eagerly at init for all string-like
          columns.  Each column is scanned independently (single-column
          projection pushdown), so this is fast even for hundreds of
          columns.
        * For larger datasets, value options are **deferred** and
          computed per-column on demand when the user clicks the filter
          icon on a column header.

        Args:
            lf: The polars LazyFrame to browse.
            descriptions: Optional ``{column: description}`` mapping for
                column header tooltips / subtitles.
            chunk_size: Number of rows to load per scroll chunk.
            value_options_max_unique: Maximum distinct values for a
                column to get a dropdown filter.
            eager_value_options_row_limit: Row count threshold below
                which value options are computed eagerly at init for all
                string-like columns.  Set to ``0`` to always defer.
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
        cache.value_options_max_unique = value_options_max_unique
        cache._value_options_cache = {}  # reset on new LazyFrame

        # Schema is cheap -- metadata only, no data scan.
        cache.schema = lf.collect_schema()

        # Build column defs from schema alone (no data scan).
        col_defs = build_column_defs_from_schema(
            cache.schema,
            column_descriptions=cache.descriptions,
        )
        cache.col_defs = [c.dict() for c in col_defs]

        self.lf_grid_columns = cache.col_defs  # type: ignore[assignment]
        self.lf_grid_loaded = True  # type: ignore[assignment]
        self._lf_grid_filter = {}  # type: ignore[assignment]
        self._lf_grid_sort = []  # type: ignore[assignment]
        self.lf_grid_filter_model = {"items": []}  # type: ignore[assignment]
        self.lf_grid_active_filter_fields = []  # type: ignore[assignment]
        self.lf_grid_pagination_model = {  # type: ignore[assignment]
            "page": 0,
            "pageSize": chunk_size,
        }
        # Refresh first page and count rows (single lightweight query).
        self._refresh_lf_grid_page(append=False, refresh_row_count=True)

        # Hybrid value options: eagerly compute for small datasets.
        if (
            eager_value_options_row_limit > 0
            and self.lf_grid_row_count <= eager_value_options_row_limit
        ):
            self._compute_all_value_options()

        self.lf_grid_loading = False  # type: ignore[assignment]
        self.lf_grid_selected_info = (  # type: ignore[assignment]
            f"Ready: {self.lf_grid_row_count:,} rows. Scroll down to load more."
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def toggle_lf_grid_debug(self) -> None:
        """Toggle the debug panel expanded/collapsed state."""
        self.lf_grid_debug_expanded = not self.lf_grid_debug_expanded  # type: ignore[assignment]

    def handle_lf_grid_filter(self, filter_model: dict[str, Any]):
        """Handle server-side filter change with multi-column accumulation.

        MUI DataGrid Community edition only sends one filter item at a
        time (``disableMultipleColumnsFiltering`` is forced ``true``).
        To support multi-column filtering on the server side, this
        handler **merges** each incoming filter item into the
        accumulated ``_lf_grid_filter`` instead of replacing it:

        * An item **with a value** upserts into the accumulated set
          (updates the existing item for that column, or adds a new one).
        * An item **without a value** for a column that already has a
          filter is ignored (the user just opened the filter panel on
          that column — the existing filter is preserved).
        * An item **without a value** for a new column is ignored (no
          filter to apply yet).
        * An **empty items list** clears all accumulated filters.

        On first filter interaction with a string column, lazily computes
        its value options (distinct values for dropdown) and updates the
        column definitions.

        This is a generator so the loading/stats state is pushed to the
        frontend *before* the potentially expensive Polars query runs.
        """
        self.lf_grid_loading = True  # type: ignore[assignment]
        self.lf_grid_stats = "Filtering..."  # type: ignore[assignment]
        yield

        # Keep the MUI frontend filter model in sync (controlled component).
        self.lf_grid_filter_model = filter_model  # type: ignore[assignment]

        # Lazily compute value options for any newly-filtered columns.
        self._ensure_value_options_for_filter(filter_model)

        merged = self._merge_filter_model(filter_model)
        self._lf_grid_filter = merged  # type: ignore[assignment]
        page_size = self.lf_grid_pagination_model.get("pageSize", _DEFAULT_CHUNK_SIZE)
        self.lf_grid_pagination_model = {"page": 0, "pageSize": page_size}  # type: ignore[assignment]
        self._refresh_lf_grid_page(append=False, refresh_row_count=True)
        self._update_filter_debug()
        self.lf_grid_loading = False  # type: ignore[assignment]

    def handle_lf_grid_sort(self, sort_model: list[dict[str, Any]]):
        """Handle server-side sort change -- reset scroll stream to top.

        This is a generator so the loading/stats state is pushed to the
        frontend *before* the potentially expensive Polars query runs.
        """
        self.lf_grid_loading = True  # type: ignore[assignment]
        self.lf_grid_stats = "Sorting..."  # type: ignore[assignment]
        yield

        self._lf_grid_sort = sort_model  # type: ignore[assignment]
        page_size = self.lf_grid_pagination_model.get("pageSize", _DEFAULT_CHUNK_SIZE)
        self.lf_grid_pagination_model = {"page": 0, "pageSize": page_size}  # type: ignore[assignment]
        self._refresh_lf_grid_page(append=False, refresh_row_count=True)
        self._update_filter_debug()
        self.lf_grid_loading = False  # type: ignore[assignment]

    def handle_lf_grid_scroll_end(self, _params: dict[str, Any]):
        """Load the next chunk when the virtual scroller nears the bottom.

        This is a generator so the loading/stats state is pushed to the
        frontend *before* the Polars query runs.
        """
        if self.lf_grid_loading:
            return

        page = self.lf_grid_pagination_model.get("page", 0)
        page_size = self.lf_grid_pagination_model.get("pageSize", _DEFAULT_CHUNK_SIZE)
        next_offset = (page + 1) * page_size
        if next_offset >= self.lf_grid_row_count:
            return

        self.lf_grid_loading = True  # type: ignore[assignment]
        self.lf_grid_stats = f"Loading rows {next_offset:,}..."  # type: ignore[assignment]
        yield

        t0 = time.perf_counter()
        self.lf_grid_pagination_model = {"page": page + 1, "pageSize": page_size}  # type: ignore[assignment]
        self._refresh_lf_grid_page(append=True, refresh_row_count=False)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        total_rows = len(self.lf_grid_rows)
        self.lf_grid_loading = False  # type: ignore[assignment]
        print(
            f"[LazyFrameGrid] scroll-end chunk: "
            f"page={page + 1}, offset={next_offset}, "
            f"+{page_size} rows, total={total_rows}, "
            f"elapsed={elapsed_ms:.1f}ms"
        )

    def handle_lf_grid_request_value_options(self, field: str) -> None:
        """Compute value options for a single column on demand.

        Dispatched from the frontend when the user clicks the filter
        icon on a column header.  If the column qualifies for a
        ``singleSelect`` dropdown (low-cardinality string/categorical),
        its column definition is upgraded in-place and pushed back to
        the frontend so MUI renders the "is" dropdown immediately.
        """
        cache_id = self._lf_grid_cache_id
        if not cache_id:
            return
        cache = _get_cache(cache_id)
        if cache.lf is None or cache.schema is None:
            return

        resolved = _resolve_field_name(field, cache.schema) if cache.schema else field
        if not resolved or resolved in cache._value_options_cache:
            return  # already computed or invalid

        options = _get_or_compute_value_options(cache, resolved)
        if options is not None:
            for i, col_def in enumerate(cache.col_defs):
                if col_def.get("field") == resolved:
                    cache.col_defs[i] = {
                        **col_def,
                        "type": "singleSelect",
                        "valueOptions": options,
                    }
                    self.lf_grid_columns = cache.col_defs  # type: ignore[assignment]
                    break

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

    def clear_lf_grid_filters(self):
        """Clear all accumulated server-side filters and the MUI grid UI.

        Resets both the backend accumulated filter and the frontend
        MUI DataGrid ``filterModel`` so the grid UI shows no active
        filter.

        This is a generator so the loading state is pushed immediately.
        """
        self.lf_grid_loading = True  # type: ignore[assignment]
        self.lf_grid_stats = "Clearing filters..."  # type: ignore[assignment]
        yield

        self._lf_grid_filter = {}  # type: ignore[assignment]
        self.lf_grid_filter_model = {"items": []}  # type: ignore[assignment]
        page_size = self.lf_grid_pagination_model.get("pageSize", _DEFAULT_CHUNK_SIZE)
        self.lf_grid_pagination_model = {"page": 0, "pageSize": page_size}  # type: ignore[assignment]
        self._refresh_lf_grid_page(append=False, refresh_row_count=True)
        self._update_filter_debug()
        self.lf_grid_loading = False  # type: ignore[assignment]

    def download_lf_grid_preset(self) -> rx.event.EventSpec:
        """Download the current filter/sort state as a JSON preset file.

        Returns an ``rx.download`` event that triggers a browser download
        of the filter state as ``filter_preset.json``.
        """
        clean_filter = self._lf_grid_filter or {}
        if clean_filter.get("items"):
            clean_filter = {
                **clean_filter,
                "items": [
                    {k: v for k, v in item.items() if k in ("field", "operator", "value")}
                    for item in clean_filter["items"]
                ],
            }
        preset: dict[str, Any] = {
            "filter_model": clean_filter,
            "sort_model": self._lf_grid_sort or [],
        }
        return rx.download(  # type: ignore[return-value]
            data=json.dumps(preset, indent=2, ensure_ascii=False),
            filename="filter_preset.json",
        )

    async def handle_lf_grid_preset_upload(self, files: list[rx.UploadFile]):
        """Handle upload of a JSON filter preset and apply it to the grid.

        Reads the uploaded JSON file, validates its structure, sets the
        filter and sort state, and refreshes the grid.

        This is an async generator so loading state is pushed to the
        frontend immediately.
        """
        if not files:
            return

        self.lf_grid_loading = True  # type: ignore[assignment]
        self.lf_grid_stats = "Applying preset..."  # type: ignore[assignment]
        yield

        upload_file = files[0]
        content = await upload_file.read()
        text = content.decode("utf-8") if isinstance(content, bytes) else content
        preset = json.loads(text)

        filter_model: dict[str, Any] = preset.get("filter_model", {})
        sort_model: list[dict[str, Any]] = preset.get("sort_model", [])

        self._lf_grid_filter = filter_model  # type: ignore[assignment]
        self._lf_grid_sort = sort_model  # type: ignore[assignment]

        # Update the MUI frontend filter model so the grid UI reflects
        # the uploaded preset.  MUI Community only shows one filter at
        # a time, so we show the last item (if any).
        items = filter_model.get("items", [])
        if items:
            last_item = items[-1]
            self.lf_grid_filter_model = {  # type: ignore[assignment]
                "items": [last_item],
                "logicOperator": filter_model.get("logicOperator", "and"),
            }
        else:
            self.lf_grid_filter_model = {"items": []}  # type: ignore[assignment]

        page_size = self.lf_grid_pagination_model.get("pageSize", _DEFAULT_CHUNK_SIZE)
        self.lf_grid_pagination_model = {"page": 0, "pageSize": page_size}  # type: ignore[assignment]
        self._refresh_lf_grid_page(append=False, refresh_row_count=True)
        self._update_filter_debug()
        self.lf_grid_loading = False  # type: ignore[assignment]

        n_filters = len(items)
        n_sorts = len(sort_model)
        self.lf_grid_selected_info = (  # type: ignore[assignment]
            f"Preset applied: {n_filters} filter(s), {n_sorts} sort(s). "
            f"{self.lf_grid_row_count:,} rows match."
        )

    def _merge_filter_model(
        self,
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge incoming filter into the accumulated ``_lf_grid_filter``.

        Delegates to the module-level :func:`merge_filter_model`.
        """
        return merge_filter_model(self._lf_grid_filter or {}, incoming)

    def _update_filter_debug(self) -> None:
        """Rebuild the compact filter/sort summary and active filter fields."""
        items: list[dict[str, Any]] = []
        if self._lf_grid_filter and self._lf_grid_filter.get("items"):
            items = self._lf_grid_filter["items"]

        active_fields: list[str] = []
        for item in items:
            field = item.get("field")
            if field:
                active_fields.append(field)
        self.lf_grid_active_filter_fields = active_fields  # type: ignore[assignment]

        # Compact one-line summary instead of verbose multi-line detail.
        parts: list[str] = []
        if items:
            logic = self._lf_grid_filter.get("logicOperator", "and").upper()
            fields = ", ".join(active_fields) if len(active_fields) <= 3 else f"{len(active_fields)} columns"
            parts.append(f"{len(items)} filter(s) ({logic}) on {fields}")
        if self._lf_grid_sort:
            sort_fields = ", ".join(e.get("field", "?") for e in self._lf_grid_sort)
            parts.append(f"{len(self._lf_grid_sort)} sort(s): {sort_fields}")
        self.lf_grid_filter_debug = " | ".join(parts) if parts else "No active filters or sorts."  # type: ignore[assignment]

        # Build the filter JSON for download/display.
        clean_filter = self._lf_grid_filter or {}
        if clean_filter.get("items"):
            clean_filter = {
                **clean_filter,
                "items": [
                    {k: v for k, v in item.items() if k in ("field", "operator", "value")}
                    for item in clean_filter["items"]
                ],
            }
        preset: dict[str, Any] = {
            "filter_model": clean_filter,
            "sort_model": self._lf_grid_sort or [],
        }
        has_content = bool(preset["filter_model"].get("items")) or bool(preset["sort_model"])
        self.lf_grid_filter_preset_json = (  # type: ignore[assignment]
            json.dumps(preset, indent=2, ensure_ascii=False) if has_content else ""
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_value_options_for_filter(
        self,
        filter_model: dict[str, Any],
    ) -> None:
        """Lazily compute value options for columns referenced in the filter.

        When the user opens a filter dropdown for a string column for the
        first time, this method computes the distinct values for that
        column (single-column scan with projection pushdown) and updates
        the column definitions sent to the frontend.

        This keeps init instant -- value options are only computed on
        demand.
        """
        cache_id = self._lf_grid_cache_id
        if not cache_id:
            return
        cache = _get_cache(cache_id)
        if cache.lf is None or cache.schema is None:
            return

        items: list[dict[str, Any]] = filter_model.get("items", [])
        columns_updated = False

        for item in items:
            raw_field = item.get("field")
            if not raw_field:
                continue
            # Resolve case-insensitively against the schema.
            field = _resolve_field_name(raw_field, cache.schema) if cache.schema else raw_field
            if not field or field in cache._value_options_cache:
                continue  # already computed or not a valid field

            options = _get_or_compute_value_options(cache, field)
            if options is not None:
                # Update the column def to singleSelect with these options.
                for i, col_def in enumerate(cache.col_defs):
                    if col_def.get("field") == field:
                        cache.col_defs[i] = {
                            **col_def,
                            "type": "singleSelect",
                            "valueOptions": options,
                        }
                        columns_updated = True
                        break

        if columns_updated:
            self.lf_grid_columns = cache.col_defs  # type: ignore[assignment]

    def _compute_all_value_options(self) -> None:
        """Eagerly compute value options for all string-like columns.

        Called at init for small datasets (row count below
        ``eager_value_options_row_limit``).  Each column is scanned
        independently with projection pushdown, so only one column is
        read at a time — the full dataset is never materialised.

        Columns that qualify are upgraded to ``singleSelect`` with
        ``valueOptions`` so the "is" dropdown is available immediately.
        """
        cache_id = self._lf_grid_cache_id
        if not cache_id:
            return
        cache = _get_cache(cache_id)
        if cache.lf is None or cache.schema is None:
            return

        t0 = time.perf_counter()
        columns_updated = False

        for col_name, dtype in cache.schema.items():
            if not isinstance(dtype, (pl.String, pl.Categorical, pl.Enum)):
                continue
            if col_name in cache._value_options_cache:
                continue
            options = _get_or_compute_value_options(cache, col_name)
            if options is not None:
                for i, col_def in enumerate(cache.col_defs):
                    if col_def.get("field") == col_name:
                        cache.col_defs[i] = {
                            **col_def,
                            "type": "singleSelect",
                            "valueOptions": options,
                        }
                        columns_updated = True
                        break

        if columns_updated:
            self.lf_grid_columns = cache.col_defs  # type: ignore[assignment]

        elapsed_ms = (time.perf_counter() - t0) * 1000
        n_computed = sum(1 for v in cache._value_options_cache.values() if v is not None)
        print(
            f"[LazyFrameGrid] eager value options: "
            f"{n_computed} columns with dropdowns ({elapsed_ms:.1f}ms)"
        )

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
        # This is a lightweight query -- Polars pushes ``select(len())``
        # into the scan for formats that support it (Parquet, IPC).
        # For VCF/CSV it does require a scan, but only counts rows
        # (no data materialisation).
        if refresh_row_count:
            t_count = time.perf_counter()
            self.lf_grid_row_count = lf.select(pl.len()).collect().item()  # type: ignore[assignment]
            cache.total_rows = self.lf_grid_row_count
            print(
                f"[LazyFrameGrid] row count: {self.lf_grid_row_count:,} "
                f"({(time.perf_counter() - t_count) * 1000:.1f}ms)"
            )

        # Apply sort.
        if self._lf_grid_sort:
            lf = apply_sort_model(lf, self._lf_grid_sort, cache.schema)

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
    show_filter_panel: bool = True,
    debug_log: bool = True,
    on_row_click: Any = None,
    **extra_props: Any,
) -> rx.Component:
    """Return a pre-wired ``data_grid(...)`` bound to a :class:`LazyFrameGridMixin` state.

    This creates a DataGrid component with server-side filtering,
    sorting, and scroll-loading already connected to the mixin's
    event handlers and state variables.

    By default the filter panel is shown below the grid.  It displays
    the active filters/sorts in human-readable form, the Filter JSON
    (copy-pasteable / downloadable), and buttons to upload a saved
    filter preset or clear all filters.  Pass
    ``show_filter_panel=False`` to hide it.

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
        show_filter_panel: Show the filter debug / Filter JSON panel
            below the grid.  Defaults to ``True``.
        debug_log: Enable browser console debug logging.
        on_row_click: Override the default row-click handler.  If ``None``,
            uses the mixin's ``handle_lf_grid_row_click``.
        **extra_props: Additional props forwarded to ``data_grid()``.

    Returns:
        A Reflex component (the grid, optionally followed by the filter panel).
    """
    if on_row_click is None:
        on_row_click = state_cls.handle_lf_grid_row_click

    grid = data_grid(
        rows=state_cls.lf_grid_rows,
        columns=state_cls.lf_grid_columns,
        row_id_field="__row_id__",
        # -- Scroll-loading mode --
        pagination=False,
        hide_footer=True,
        filter_mode="server",
        sorting_mode="server",
        # -- Controlled filter model (so "Clear All" resets the MUI UI) --
        filter_model=state_cls.lf_grid_filter_model,
        # -- Active filter fields (highlights filter icons in column headers) --
        active_filter_fields=state_cls.lf_grid_active_filter_fields,
        # -- Display --
        loading=state_cls.lf_grid_loading,
        show_toolbar=show_toolbar,
        show_description_in_header=show_description_in_header,
        always_show_filter_icon=True,
        density=density,
        column_header_height=column_header_height,
        scroll_end_threshold=scroll_end_threshold,
        debug_log=debug_log,
        # -- Events --
        on_rows_scroll_end=state_cls.handle_lf_grid_scroll_end,
        on_filter_model_change=state_cls.handle_lf_grid_filter,
        on_sort_model_change=state_cls.handle_lf_grid_sort,
        on_request_value_options=state_cls.handle_lf_grid_request_value_options,
        on_row_click=on_row_click,
        height=height,
        width=width,
        **extra_props,
    )

    if not show_filter_panel:
        return grid

    return rx.fragment(
        grid,
        lazyframe_grid_filter_debug(state_cls),
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


def lazyframe_grid_filter_debug(state_cls: type) -> rx.Component:
    """Return a collapsible debug panel showing active filters and sorts.

    The header bar is always visible and shows a compact one-line summary
    plus Clear / Upload buttons.  Clicking the chevron expands the panel
    to reveal the full Filter JSON (copy-pasteable / downloadable).

    Args:
        state_cls: The ``rx.State`` subclass that inherits from
            :class:`LazyFrameGridMixin`.

    Returns:
        A Reflex component.
    """
    upload_id = f"preset_upload_{state_cls.__name__}"

    header = rx.hstack(
        rx.button(
            rx.cond(
                state_cls.lf_grid_debug_expanded,
                rx.icon("chevron_down", size=14),
                rx.icon("chevron_right", size=14),
            ),
            size="1",
            variant="ghost",
            color_scheme="orange",
            on_click=state_cls.toggle_lf_grid_debug,
            padding="2px",
        ),
        rx.icon("bug", size=14, color="var(--orange-9)"),
        rx.text(
            state_cls.lf_grid_filter_debug,
            size="1",
            color="var(--orange-11)",
            white_space="nowrap",
            overflow="hidden",
            text_overflow="ellipsis",
            flex="1 1 auto",
            min_width="0",
        ),
        rx.spacer(),
        rx.upload(
            rx.button(
                rx.icon("upload", size=14),
                "Upload",
                size="1",
                variant="outline",
                color_scheme="blue",
            ),
            id=upload_id,
            accept={".json": ["application/json"]},
            max_files=1,
            no_drag=True,
            on_drop=state_cls.handle_lf_grid_preset_upload(  # type: ignore[attr-defined]
                rx.upload_files(upload_id=upload_id)
            ),
            padding="0",
            border="none",
        ),
        rx.button(
            rx.icon("x", size=14),
            "Clear All",
            size="1",
            variant="outline",
            color_scheme="orange",
            on_click=state_cls.clear_lf_grid_filters,
        ),
        align="center",
        spacing="2",
        width="100%",
    )

    expanded_content = rx.cond(
        state_cls.lf_grid_debug_expanded,
        rx.cond(
            state_cls.lf_grid_filter_preset_json != "",
            rx.box(
                rx.hstack(
                    rx.icon("braces", size=14, color="var(--orange-9)"),
                    rx.text(
                        "Filter JSON",
                        size="1",
                        weight="bold",
                        color="var(--orange-11)",
                    ),
                    rx.spacer(),
                    rx.button(
                        rx.icon("clipboard_copy", size=12),
                        "Copy",
                        size="1",
                        variant="ghost",
                        color_scheme="orange",
                        on_click=rx.set_clipboard(state_cls.lf_grid_filter_preset_json),  # type: ignore[arg-type]
                    ),
                    rx.button(
                        rx.icon("download", size=12),
                        "Download",
                        size="1",
                        variant="ghost",
                        color_scheme="orange",
                        on_click=state_cls.download_lf_grid_preset,
                    ),
                    align="center",
                    spacing="2",
                    width="100%",
                ),
                rx.code_block(
                    state_cls.lf_grid_filter_preset_json,
                    language="json",
                    show_line_numbers=False,
                    wrap_long_lines=True,
                ),
                margin_top="0.5em",
            ),
        ),
    )

    return rx.box(
        header,
        expanded_content,
        padding="0.5em 0.8em",
        border_radius="8px",
        background="var(--orange-a2)",
        border="1px solid var(--orange-a5)",
        margin_top="0.5em",
        margin_bottom="0.5em",
    )


def merge_filter_model(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    """Merge an incoming MUI filter model into an accumulated filter.

    MUI DataGrid Community edition only sends one filter item at a
    time.  This function merges each incoming item into the existing
    accumulated set, keyed by ``field``:

    * Incoming item **has a value** → upsert (replace or add) for
      that field.
    * Incoming item **has no value** and the field already has a
      filter → keep the existing filter (user just opened the panel).
    * Incoming item **has no value** and the field is new → ignore.
    * Incoming items list is **empty** → clear all accumulated filters.

    Args:
        existing: The previously accumulated filter model (may be
            empty ``{}``).
        incoming: The new filter model from MUI's
            ``onFilterModelChange`` callback.

    Returns:
        The merged filter model dict, or ``{}`` if no filters remain.
    """
    incoming_items: list[dict[str, Any]] = incoming.get("items", [])
    logic: str = incoming.get("logicOperator", "and")

    if not incoming_items:
        return {}

    existing_items: list[dict[str, Any]] = existing.get("items", []) if existing else []
    by_field: dict[str, dict[str, Any]] = {}
    for item in existing_items:
        field = item.get("field")
        if field:
            by_field[field] = item

    for item in incoming_items:
        field = item.get("field")
        if not field:
            continue

        has_value = item.get("value") is not None
        operator = item.get("operator", "")
        valueless_ops = {"isEmpty", "isNotEmpty"}
        if operator in valueless_ops:
            has_value = True

        if has_value:
            # Item has a value (or is a valueless operator) — upsert.
            by_field[field] = item
        elif field in by_field:
            # Item has no value but the field already has a filter.
            # Check if the operator changed — if so, update the operator
            # on the existing filter item.  This prevents the UI from
            # "snapping back" to the old operator (e.g. "=" instead of
            # ">") when the user changes the operator dropdown.
            existing_op = by_field[field].get("operator", "")
            if operator and operator != existing_op:
                by_field[field] = {**by_field[field], "operator": operator}

    merged_items = list(by_field.values())
    if not merged_items:
        return {}

    return {
        "items": merged_items,
        "logicOperator": logic,
    }


def _format_filter_model_debug(filter_model: dict[str, Any]) -> str:
    """Format a MUI filter model dict into a human-readable debug string."""
    lines: list[str] = []
    items: list[dict[str, Any]] = filter_model.get("items", []) if filter_model else []
    if items:
        logic = filter_model.get("logicOperator", "and").upper()
        lines.append(f"FILTERS ({logic}):")
        for i, item in enumerate(items):
            field = item.get("field", "?")
            op = item.get("operator", "?")
            val = item.get("value")
            val_str = repr(val) if val is not None else "(empty)"
            lines.append(f"  {i + 1}. {field} {op} {val_str}")
    else:
        lines.append("FILTERS: none")
    return "\n".join(lines)


def _format_sort_model_debug(sort_model: list[dict[str, Any]]) -> str:
    """Format a MUI sort model list into a human-readable debug string."""
    lines: list[str] = []
    if sort_model:
        lines.append("SORTS:")
        for i, entry in enumerate(sort_model):
            field = entry.get("field", "?")
            direction = entry.get("sort", "asc")
            lines.append(f"  {i + 1}. {field} {direction}")
    else:
        lines.append("SORTS: none")
    return "\n".join(lines)


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
