# Agent Guidelines

This project is uv based, it is a reflex wrapper for mui x-data-grid UI component

## Reflex-Specific Patterns (CRITICAL)

- **State var mixin classes MUST use `rx.State` with `mixin=True`**: Reflex provides a built-in mixin mechanism. Declare your mixin as `class MyMixin(rx.State, mixin=True)` so that the vars are **not** registered on the mixin itself but are injected into each concrete subclass by Reflex's metaclass. Each subclass then gets its own independent set of reactive vars. Subclasses **must** also inherit from `rx.State` (or another non-mixin state class) so the mixin flag is cleared and vars become reactive:
  ```python
  # CORRECT — mixin=True, each child gets independent vars
  class MyMixin(rx.State, mixin=True):
      my_count: int = 0

  class GridA(MyMixin, rx.State):
      ...
  class GridB(MyMixin, rx.State):
      ...
  # GridA.my_count and GridB.my_count are INDEPENDENT rx.Var objects

  # WRONG — without mixin=True, all children share the SAME vars
  class MyMixin(rx.State):
      my_count: int = 0

  class GridA(MyMixin):
      ...
  class GridB(MyMixin):
      ...
  # GridA.my_count and GridB.my_count point to the SAME reactive var

  # ALSO WRONG — plain Python mixin without rx.State, vars stay as raw types
  class MyMixin:
      my_count: int = 0

  class AppState(MyMixin, rx.State):
      ...
  # AppState.my_count is just int(0), .to(str) crashes
  ```

- **No keyword-only arguments in mixin event handler methods**: Reflex's `BaseState._copy_fn` copies event handler methods from mixin classes to concrete subclasses using `FunctionType(..., argdefs=fn.__defaults__)`. This copies `__defaults__` (positional defaults) but **not** `__kwdefaults__` (keyword-only defaults). If a mixin method uses `*,` to define keyword-only arguments with defaults, those defaults are silently lost when the method is copied to the child class, causing `TypeError: missing required keyword-only arguments`. Always use regular positional arguments with defaults instead of keyword-only arguments in mixin methods that will be used as event handlers.

- **`pagination=False` for scrollable grids**: The `WrappedDataGrid` defaults to `pagination=True` and `auto_page_size=True`. You MUST explicitly pass `pagination=False` and `hide_footer=True` to get a continuously scrollable grid. Without this, rows are silently paginated and only the first page is visible.

- **Column definitions stored in state vars MUST be JSON-serializable**: Storing `ColumnDef` objects or `rx.Var`-based renderers in state vars (e.g. `prs_columns`) fails because Reflex cannot serialize them. Use `cell_renderer_type` + `cell_renderer_config` (plain strings/dicts) for columns that go through state; keep `rx.Var`-based renderers only for static, compile-time column definitions.

- **New public APIs must be exported in `__init__.py`**: When adding new classes (e.g. `BadgeCellRenderer`, `ProgressBarCellRenderer`), they must be added to `reflex_mui_datagrid/__init__.py` so they can be imported by users. Missing exports cause `ImportError`.

## LazyFrame Grid Requirements (CRITICAL)

- **Truly lazy behavior**: `set_lazyframe` and all grid operations MUST be memory-safe. NEVER collect the entire LazyFrame. Every operation (row count, value options inference, page slicing) must use lazy queries that Polars can push down into the scan. If a full-dataset scan is unavoidable (e.g. counting rows on a format without metadata), it must be a streaming count — never materialise all rows into a DataFrame.
- **Hybrid value options strategy**: Value options for filter dropdowns (the "is" dropdown with singleSelect) use a two-tier approach:
  * **Small datasets** (row count <= `eager_value_options_row_limit`, default 50k): value options are computed eagerly at `set_lazyframe` init for all string-like columns. Each column is scanned independently with projection pushdown — the full dataset is never materialised. Columns that qualify are marked `singleSelect` immediately so the "is" dropdown is available from the start.
  * **Large datasets**: value options are deferred and computed on demand when the user clicks the filter icon on a column header. The JS `_AlwaysVisibleFilterIconButton` dispatches a `_requestValueOptions` custom event which the `UnlimitedDataGrid` wrapper forwards to `handle_lf_grid_request_value_options(field)`. This upgrades the column to `singleSelect` with `valueOptions` and pushes updated column defs to the frontend.
  * The `_ensure_value_options_for_filter` fallback still runs on filter apply as a safety net for columns not yet computed.
- **Always-visible filter buttons in column headers**: Every column header must have a clickable filter icon/button on the right side of the header text. Clicking it opens the filter panel for that column. These buttons must always be visible (not hidden behind a hover or menu). This is a core UX requirement — users must see at a glance that columns are filterable and be able to filter with one click.
- **Memory safety**: The grid must never hold more rows in memory (in `lf_grid_rows`) than what has been scrolled to. Each scroll chunk appends only the new slice. Filter/sort resets must clear accumulated rows and start fresh from offset 0.

## Server-Side Filter Architecture (CRITICAL)

- **Apply button pattern**: When `filterMode="server"`, the grid uses a custom `_FilterPanelWithApply` slot that adds Apply/Reset buttons below the standard `GridFilterPanel`. The `UnlimitedDataGrid` wrapper intercepts `onFilterModelChange` — user edits update a local React state only (no Python call), and the real Python callback is only invoked when Apply is clicked (or Enter is pressed). This prevents expensive server queries on every keystroke.
- **Local filter model**: In server filter mode, the controlled `filterModel` prop from Python is replaced with a local React state (`localFilterModel`). This local state syncs from the Python prop only when the prop genuinely changes (detected via `JSON.stringify` comparison). This prevents MUI from resetting the user's in-progress edits when unrelated state vars (like `lf_grid_loading`) cause re-renders.
- **Custom event dispatch**: The Apply button dispatches a `_applyFilter` CustomEvent (with `bubbles: true`) on the MUI grid root element. The `UnlimitedDataGrid` wrapper listens for this event on its container div and forwards the filter model to the real Python `onFilterModelChange` callback.
- **Operator preservation in merge_filter_model**: When MUI sends a filter item with a changed operator but no value (user changed the operator dropdown), `merge_filter_model` updates the operator on the existing accumulated filter item instead of ignoring the change. This prevents the operator from "snapping back" to the previous value.
- **Filter panel must close on Apply/Reset**: When the user clicks Apply or Reset in the filter panel, the panel must close automatically. Use `apiRef.current.hideFilterPanel()` after dispatching the filter event.
- **Default operator for singleSelect columns**: For enum-like (`singleSelect`) columns (e.g. chromosome), default the filter operator to `"is"` unless the user changes it. Avoid leaving the operator empty.
- **Case-insensitive field name resolution (CRITICAL)**: Reflex's serialisation layer may convert column names to different cases (e.g. `DP` → `dp`, `MIN_DP` → `min_dp`). All filter/sort/value-options code MUST use `_resolve_field_name(raw_field, schema)` to resolve field names case-insensitively against the schema before using them in Polars expressions. Never do `if field not in schema` directly — always resolve first. The canonical column name from the schema must be used in `pl.col(field)` calls to avoid DataFusion predicate pushdown errors.

## MUI X Internals

- **`setPanels` exists in the Community edition virtualizer**: The `setPanels` API lives in `@mui/x-virtualizer` (the shared virtualizer package used by all editions), not gated behind a Pro license. It is a React `useState` setter accepting `Map<GridRowId, ReactNode>`. After rendering each row, the virtualizer checks `panels.get(id)` and appends the panel element. Access it via `apiRef.current.virtualizer.api.getters.setPanels`. This is how MUI Pro implements detail panels — the Pro package only adds `GridDetailPanels` which calls `setPanels`.
- **Detail panels must not inflate the host row height**: The custom Community detail panel should keep using `setPanels(map)` for the panel content, but must not also return `base row height + detail panel height` from `getRowHeight`. MUI renders the panel below the row, so inflating the host row double-counts space and creates a giant blank spacer.
- **`rowSelectionModel` requires Set conversion**: MUI DataGrid v8 expects `rowSelectionModel.ids` as a `Set<GridRowId>`, but Python/JSON sends arrays. The JS wrapper must convert arrays to `Set` before passing to MUI.
- **`row_id_field` with spaces needs bracket notation**: When `row_id_field` contains spaces (e.g. `"PGS ID"`), use `row["PGS ID"]` in JS instead of dot notation to avoid invalid JavaScript.

## Host layout: internal vertical scroll + detail panels (Reflex)

`WrappedDataGrid` / `data_grid(...)` pops `height` onto an outer wrapper (often `height="100%"`). **Percentage height only works if every ancestor has a definite height** (fixed length, flex allocation, or chain of `%` back to a sized root).

**Symptom:** With expanded row detail panels (`detail_columns` / `setPanels`), the **grid loses its vertical scrollbar**, the **page** scrolls instead, or you **cannot scroll to other rows** — especially after layout changes or on tall viewports.

**Root cause (host app, not MUI internals):** A flex item around the grid with **`flex: 1 1 auto`** uses **content-based flex-basis**. Tall expanded detail content increases that item’s intrinsic minimum height, so the **grid shell grows with the accordion** instead of staying within the tab/viewport. `max_height` alone (including `vh`/`calc`) does **not** fix participation of intrinsic height in the same way as a **zero flex-basis** slot.

**Fix pattern (copy into any similar page):**

1. Outer column: `display="flex"`, `flex_direction="column"`, **`height="calc(100vh - <chrome>)`**, **`min_height="0"`** (and optional `gap`).
2. **Non-growing blocks** above/below the grid (titles, toolbars, stats): wrap or style with **`flex_shrink="0"`**.
3. **Grid shell** `rx.box`: **`flex="1 1 0%"`**, **`min_height="0"`**, **`overflow="hidden"`**, **`width="100%"`** — takes **only remaining column space**, not content-driven height.
4. **`data_grid(..., height="100%", pagination=False, hide_footer=True, …)`** as usual.

**Reusable prompt (paste into an assistant):** *“MUI X DataGrid in Reflex with reflex-mui-datagrid: expanded detail panels broke internal vertical scrolling / page steals scroll. Parent uses flex column and WrappedDataGrid with height 100%. Apply the flex `1 1 0%` + `min_height 0` + `overflow hidden` grid shell pattern; bounded viewport column root `calc(100vh - chrome)`. Diagnose host CSS flex basis before changing pagination or datagrid.js.”*

## Bell Curve Renderer (CRITICAL)

The `bell_curve` detail renderer (`_BellCurveRenderer` in `datagrid.py`) draws a Plotly normal distribution with per-point markers, a "your score" line, and population/model labels. It has a strict separation between **layout** (chart aspect, margins, legend, y-axis range) and **label placement** (collision-aware annotations). Both have configurable knobs, but **layout defaults are sacred** — they preserve the historical bell curve aspect and must not be changed casually.

- **Layout defaults must match the original curve**. The defaults are `marginTop: 18`, `marginBottom: 48`, `legendY: -0.22`, `yAxisMax: 0.45`, no `xTitleStandoff`. Apps may override these via the renderer config (`marginTop`, `marginBottom`, `legendY`, `yAxisMax`, `xTitleStandoff`) only when they explicitly need more headroom for very dense label stacks. Changing the defaults squashes the bell curve into a smaller proportion of the chart. The test `test_bell_curve_layout_defaults_preserve_original_curve` pins these values; if you touch them, you must justify why and update the test.
- **Label placement uses a 3-column-grid collision algorithm** (`_bellCurveLabelOffset`). For each label, the algorithm finds the first non-colliding slot in this order: tier 0 = center / row 0, tier 1 = left / row 0, tier 2 = right / row 0, tier 3 = center / row 1, tier 4 = left / row 1, … . Close-by labels separate horizontally *before* stacking into higher rows, so chart top margin stays small. Two labels collide when `|z_a - z_b| < labelMinGapZ` (default `0.24` z-units). Knobs: `labelTiers` (max total slots, default 9), `labelMinGapZ`, `labelYOffset` (px above marker for row 0, default 22), `labelYOffsetStep` (px per additional row, default 18), `labelXOffsetStep` (px per left/right side, default 24).
- **Label visibility knobs**: `labelMode` (`"auto"`, `"always"`, `"none"`) and `labelMaxVisible` control whether inline point labels are drawn. In `"auto"` mode, charts with more than `labelMaxVisible` points hide inline labels but keep the legend and hover text. Use `"always"` for small population panels where every label must be visible; use `"none"` or rely on `labelMaxVisible` for dense trait-aggregation charts.
- **Personal score labels have priority over population labels**. `_BellCurveRenderer` computes the personal score position before placing population labels, reserves nearby label tiers with `scoreLabelReservedTiers` (default 3), and renders the score annotation last so it appears above everything else. Defaults: `scoreLabelFontSize=13`, `scoreLabelYOffset=26`, `scoreLabelXOffset=0`, white-ish `scoreLabelBgColor`, orange border. Keep the personal score label bold and larger than population labels; if it overlaps in a dense chart, tune `scoreLabelReservedTiers` or `scoreLabelYOffset` before changing chart layout. Do not set the default `scoreLabelYOffset` so high that it clips against the fixed top margin.
- **Per-point styling on `TonedItem` is honored**: `markerColor`, `markerSize`, and `symbol` on each `items` entry pass through to the marker trace and label arrow color. Outlier items override these with the standard red diamond unless explicitly set.
- **`data.rendererConfig` / `data.config` enables row-level overrides** (merged on top of the column-level renderer config). Use this in Python state code when a single row needs different chart sizing or label behavior — e.g. a trait with 8 PRS models switches to a wider layout via `percentile_chart["rendererConfig"] = {"height": 520, "maxWidth": 1800, "labelTiers": 12, ...}`. Do not push layout overrides through `data.rendererConfig` unless you actually need them; prefer label-only knobs.
- **`summaryPlacement` controls where `data.summary` appears**: `"sidePanel"` (default) keeps it inside the side-panel card stack, `"fullWidth"` renders it as a wrapped block below the chart and side panel, `"chart"` puts it directly under the chart, `"none"` hides it. Use `"fullWidth"` when summary text is long and would crowd the side panel.
- **`DetailRendererConfig` model exposes all knobs**: snake_case Python fields map to camelCase JS keys in `model_dump()`. New knobs added to the renderer must also be added to `DetailRendererConfig` in `models.py` and aliased in `model_dump()` so Pydantic users get type checking and IDE autocomplete.

## Failed Hypotheses (do NOT repeat)

- **CSS-only fixes for column header icon alignment DO NOT WORK**: Adding `flex: 1 1 auto` to `.MuiDataGrid-columnHeaderTitleContainerContent` via MUI `sx` prop, global `<style>` injection with `!important`, or generic CSS selectors (`:first-child:not(...)`, `:not(...)`) all fail to push filter/sort icons to the right edge when `renderHeader` produces two-line headers (name + description). MUI v8's styled-component output overrides `sx` regardless of specificity. The **working approach** is a `ref` callback on the `renderHeader` div that imperatively sets `flex: 1 1 auto` on the parent `columnHeaderTitleContainerContent` DOM element (see `_forceParentFlex`).
- **Synthetic detail rows injected into the rows array DO NOT WORK**: Injecting `__is_detail_row__` synthetic rows into the grid's `rows` array and overriding `getRowHeight`/`getRowClassName`/`renderCell` to render detail content causes severe performance issues and visual overlay glitches. MUI's virtualizer fights the injected rows. The correct approach is to use the `setPanels` API from `@mui/x-virtualizer` (see MUI X Internals above).
- **Expanded detail host-row height inflation DO NOT WORK**: Combining `setPanels(map)` with custom `getRowHeight` logic that adds the detail panel height to the host row creates a huge blank row because the panel is already rendered separately below the row.
- **Paginated fallback for `pagination=False` DO NOT WORK**: Falling back to `autoPageSize` pagination when the unlimited-grid patch is inactive traps lazy-grid users on a small manual page (for example `1-8 of 114`) even though the backend loaded all rows. For dynamic scrolling, always forward `pagination=false`, `autoPageSize=false`, and a hidden footer to MUI; let MUI virtualization handle the currently loaded rows while `LazyFrameGrid` appends more chunks.
- **Changing bell curve layout defaults (`marginTop`, `marginBottom`, `legendY`, `yAxisMax`) to fix overlapping labels DOES NOT WORK and breaks the curve**: Increasing top/bottom margins or expanding the y-axis range to make room for labels visibly squashes the bell curve into a smaller fraction of the chart, changing the curve's aspect and visual proportion. Users notice immediately. The correct fix is to update only the **label placement algorithm** (`_bellCurveLabelOffset`) — bigger horizontal stagger, more vertical tiers, smarter collision detection. Treat layout defaults as immutable defaults; expose them as configurable knobs for the rare app that genuinely needs more headroom, but never change the defaults to paper over a label issue.
- **Vertical-only label stacking with small step (`labelYOffsetStep < 16`) overlaps labels visually**: Population/model labels are ~12–14 px tall; stacking at 13 px increments leaves them touching. Either use a 3-column grid (center / left / right at each row, so close-by labels separate horizontally before stacking) or use `labelYOffsetStep ≥ 16`. Pure horizontal staggering with no vertical tier produces arrow lines that cross every other label arrow. The shipped algorithm combines both: spread horizontally first, then stack vertically only when the grid row is full.
- **`flex: 1 1 auto` on the grid wrapper + tall detail panels DO NOT preserve grid-internal vertical scroll**: Intrinsic height from expanded panels participates in sizing; the wrapper grows and MUI no longer behaves like a fixed-height viewport. Use **`flex: 1 1 0%`**, **`min-height: 0`**, **`overflow: hidden`** on the grid shell inside a **height-bounded** column flex parent — see **Host layout: internal vertical scroll + detail panels** above. Do not assume **`max_height`** alone fixes flex basis behavior.

## Coding Standards

- **Avoid nested try-catch**: try catch often just hide errors, put them only when errors is what we consider unavoidable in the use-case.
- **Type hints**: Mandatory for all Python code.
- **Pathlib**: Always use for all file paths.
- **No relative imports**: Always use absolute imports.
- **No placeholders**: Never use `/my/custom/path/` in code.
- **No legacy support**: Refactor aggressively; do not keep old API functions.
- **Publishing to PyPI**: The PyPI publish token is stored in `.env` as `PYPI_TOKEN`. Source the file before publishing: `set -a && source .env && set +a && uv publish --token "$PYPI_TOKEN" dist/PACKAGE_FILES`. Note that `.env` values are quoted — you must `source` the file (not just export the raw string) so the shell strips the quotes.
- **Dependency Management**: Use `uv sync` and `uv add`. NEVER use `uv pip install`.
- **Versions**: Do not hardcode versions in `__init__.py`; use `pyproject.toml`.
- **Avoid __all__**: Avoid `__init__.py` with `__all__` as it confuses where things are located.
- **Pay attention to terminal warnings**: Always check terminal output for warnings, especially deprecation ones. AI knowledge of APIs can be outdated; these warnings are critical hints to update code to the current version.
- **Typer CLI**: Mandatory for all CLI tools.
- **Pydantic 2**: Mandatory for data classes.
- **Self-Correction**: If you make an API mistake that leads to a system error (e.g. a crash or a major logic failure due to outdated knowledge), you MUST update this file (`AGENTS.md`) with the correct API usage or pattern. This ensures future agents don't repeat the same mistake.
- **Docs**: Put all new markdown files (except README/AGENTS) in `docs/`.

## Test Generation Guidelines

- **Real data + ground truth**: Use actual source data, auto-download if needed, and compute expected values at runtime.
- **Deterministic coverage**: Use fixed seeds or explicit filters; include representative and edge cases.
- **Meaningful assertions**: Prefer relationships and aggregates over existence-only checks.
- **Verbosity**: Run `pytest -vvv`.

### What to Validate

- **Counts & aggregates**: Row counts, sums/min/max/means, distinct counts, and distributions.
- **Joins**: Pre/post counts, key coverage, cardinality expectations, nulls introduced by outer joins, and a few spot-checks.
- **Transformations**: Round-trip survival, subset/superset semantics, value mapping, key preservation.
- **Data quality**: Format/range checks, outliers, malformed entries, duplicates, referential integrity.

### Avoiding LLM "Reward Hacking" in Tests

- **Runtime ground truth**: Query source data at test time instead of hardcoding expectations.
- **Seeded sampling**: Validate random records with a fixed seed, not just known examples.
- **Negative & boundary tests**: Ensure invalid inputs fail; probe min/max, empty, unicode.
- **Derived assertions**: Test relationships (e.g., input vs output counts), not magic numbers.
- **Allow expected failures**: Use `pytest.mark.xfail` for known data quality issues with a clear reason.

### Test Structure Best Practices

- **Parameterize over duplicate**: If testing the same logic on multiple outputs, use `@pytest.mark.parametrize` instead of copy-pasting tests.
- **Set equality over counts**: Prefer `assert set_a == set_b` over `assert len(set_a) == 270` - set comparison catches both missing and extra values.
- **Delete redundant tests**: If test A (e.g., set equality) fully covers test B (e.g., count check), keep only test A.
- **Domain constants are OK**: Hardcoding expected enum values or well-known constants from specs is fine; hardcoding row counts or unique counts derived from data inspection is not.

### Verifying Bug-Catching Claims

When claiming a test "would have caught" a bug, **demonstrate it**:

1. **Isolate the buggy logic** in a test or script
2. **Run it and show failure** against correct expectations
3. **Then show the fix passes** the same test

Never claim "tests would have caught this" without running the buggy code against the test.

### Anti-Patterns to Avoid

- Testing only "happy path" with trivial data
- Hardcoding expected values that drift from source (use derived ground truth)
- Mocking data transformations instead of running real pipelines
- Ignoring edge cases (nulls, empty strings, boundary values, unicode, malformed data)
- **Claiming tests "would catch bugs" without demonstrating failure on buggy code**

**Meaningless Tests to Avoid** (common AI-generated anti-patterns):

## Learned User Preferences

- **Never assume the user didn't rebuild**: When a fix doesn't appear to work in the browser, do not suggest the user forgot to rebuild or update the code. Investigate the actual problem instead, including stale compiled frontend output or multiple running demo servers.
- **Trust user-provided DOM structure**: When the user provides DOM paths or structure from their browser, prefer that information over automated browser inspection which can be unreliable.
- **Precise scope when removing code**: When asked to remove a specific feature, remove only what was asked. Do not remove adjacent related functionality unless explicitly requested.
- **Extend the library rather than working around it**: If a feature exists in the TypeScript MUI DataGrid but not in the Reflex wrapper, extend the library to support it rather than building hacky workarounds.
- **Provide demos for new features**: New features should be demonstrated in the existing demo app (e.g. genetic variants/PRS tab) rather than only documented.
- **Never revert always-visible filter icons to MUI default**: The custom always-visible filter icon buttons in column headers are a core UX requirement. Never replace them with MUI's default hover-only behavior.
- **Document failed hypotheses immediately**: When an approach fails, document it in the Failed Hypotheses section of AGENTS.md to prevent future agents from retrying the same approach.
- **README ordering**: Keep the README focused on the most common library usage first, and move specialized workflows, genomic examples, demos, and deeper API material lower down.

## Learned Workspace Facts

- **Demo app**: Run with `uv sync` then `uv run demo` from the project root. The demo uses `workspace = true` in `pyproject.toml` to depend on the local repo version.
- **Filter JSON `id` field**: The `id` in MUI filter items is MUI-internal and should be stripped from filter JSON output sent to the user.
- **Dynamic scrolling monkey-patching**: Dynamic scrolling with `pagination=False` originally used monkey-patching of MUI's pagination logic; this broke when Reflex switched from Next.js to Vite/ESM (CommonJS `require()` no longer available).
- **MUI DataGrid package**: The wrapper targets MUI X DataGrid Community v8 and installs `@mui/x-data-grid@^8.27.0`; imports should still render from bare `@mui/x-data-grid` with `ImportVar(..., install=False)`. Accidentally resolving MUI X 9.x breaks wrapper internals.
- **Filter panel switches**: `lazyframe_grid(show_filter_panel=False)` hides the whole filter panel, while `show_filter_presets=False` keeps the filter summary and Clear All button but hides JSON upload/copy/download controls.
- **Server-side toolbar default**: `lazyframe_grid` defaults `show_toolbar=False` because MUI toolbar search/export operate only on browser-loaded rows, not the full server-side LazyFrame result; if explicitly enabled in server mode, quick search is hidden by default.
- **Column overrides and URL suffixes**: `set_lazyframe(column_overrides=...)` applies overrides into `cache.col_defs` before syncing columns so lazy value-option updates preserve widths/renderers; URL renderers support `suffixUrl` / `suffix_url` for trailing path segments.
- **Non-filterable lazy-grid fields**: Use `set_lazyframe(non_filterable_fields=[...])` or `ColumnDef.filterable=False` to suppress the custom header filter icon, lazy value-options computation, and server-side filter application for those fields.
- **Inline JS in Python strings**: Avoid unescaped JS regex sequences such as `\s`, `\d`, `\w`, or `\-` inside Python triple-quoted strings; use alternatives like `[ \t]`, place `-` at the end of character classes, or double-escape backslashes before compiling.
- **Reflex version checks**: In Reflex 0.9+, do not rely on `reflex.__version__`; use `uv run reflex --version` or `importlib.metadata.version("reflex")`.
- **Column autosizing pitfalls**: MUI `autosizeOnMount` and programmatic `apiRef.current.autosizeColumns()` were unreliable in the unlimited grid flow and can fight `minWidth`; avoid relying on them for readable lazy-grid column sizing.
- **Bell curve label collision algorithm is a 3-column grid**: `_bellCurveLabelOffset` packs labels into tiers (center / left / right repeated upward). The defaults `labelTiers=9`, `labelMinGapZ=0.24`, `labelYOffset=22`, `labelYOffsetStep=18`, `labelXOffsetStep=24` handle most charts without bumping chart margins. Per-row overrides (e.g. `labelTiers=12`, `labelMinGapZ=0.18`) are the right tool for dense trait-aggregation charts, not changes to the layout defaults.
- **Bell curve personal score label wins collisions**: `_BellCurveRenderer` reserves `scoreLabelReservedTiers` around the score z-position before placing population labels, then renders the score annotation last with bold larger text and a background. Defaults are `scoreLabelFontSize=13`, `scoreLabelYOffset=26`, and `scoreLabelReservedTiers=3`; higher offsets need matching top margin/headroom to avoid clipping.
- **Bell curve layout defaults (marginTop=18, marginBottom=48, legendY=-0.22, yAxisMax=0.45)**: These pin the original bell curve aspect. They are exposed via `DetailRendererConfig` for explicit overrides per chart but should never be changed at the renderer-default level. The test `test_bell_curve_layout_defaults_preserve_original_curve` enforces this.
- **Per-point marker styling on `TonedItem`**: `markerColor`, `markerSize`, and `symbol` on items pass through to both the Plotly marker trace and the label arrow color. Outlier items get a red diamond by default unless `symbol` is explicitly set.
