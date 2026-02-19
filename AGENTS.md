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
- **Case-insensitive field name resolution (CRITICAL)**: Reflex's serialisation layer may convert column names to different cases (e.g. `DP` → `dp`, `MIN_DP` → `min_dp`). All filter/sort/value-options code MUST use `_resolve_field_name(raw_field, schema)` to resolve field names case-insensitively against the schema before using them in Polars expressions. Never do `if field not in schema` directly — always resolve first. The canonical column name from the schema must be used in `pl.col(field)` calls to avoid DataFusion predicate pushdown errors.

## Failed Hypotheses (do NOT repeat)

- **CSS-only fixes for column header icon alignment DO NOT WORK**: Adding `flex: 1 1 auto` to `.MuiDataGrid-columnHeaderTitleContainerContent` via MUI `sx` prop, global `<style>` injection with `!important`, or generic CSS selectors (`:first-child:not(...)`, `:not(...)`) all fail to push filter/sort icons to the right edge when `renderHeader` produces two-line headers (name + description). MUI v8's styled-component output overrides `sx` regardless of specificity.  The **working approach** is a `ref` callback on the `renderHeader` div that imperatively sets `flex: 1 1 auto` on the parent `columnHeaderTitleContainerContent` DOM element (see `_forceParentFlex`).

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
