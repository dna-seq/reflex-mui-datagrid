# Agent Guidelines

This project is uv based, it is a reflex wrapper for mui x-data-grid UI component

## Reflex-Specific Patterns (CRITICAL)

- **State var mixin classes MUST extend `rx.State`**: Reflex's metaclass only wraps class-level annotated attributes into reactive `rx.Var` objects for classes that inherit from `rx.State`. If you create a mixin with state vars as a plain Python class, those vars will remain raw Python defaults (e.g. `int`, `str`, `list`) when accessed on the subclass, and calls like `.to(str)` or reactive comparisons (`!= ""`) will fail at component build time. **Always** make state mixins inherit from `rx.State`:
  ```python
  # CORRECT — vars become reactive rx.Var objects
  class MyMixin(rx.State):
      my_count: int = 0

  class AppState(MyMixin):
      ...
  # AppState.my_count is an rx.Var, .to(str) works

  # WRONG — vars stay as plain Python types
  class MyMixin:
      my_count: int = 0

  class AppState(MyMixin, rx.State):
      ...
  # AppState.my_count is just int(0), .to(str) crashes
  ```

- **`pagination=False` for scrollable grids**: The `WrappedDataGrid` defaults to `pagination=True` and `auto_page_size=True`. You MUST explicitly pass `pagination=False` and `hide_footer=True` to get a continuously scrollable grid. Without this, rows are silently paginated and only the first page is visible.

## LazyFrame Grid Requirements (CRITICAL)

- **Truly lazy behavior**: `set_lazyframe` and all grid operations MUST be memory-safe. NEVER collect the entire LazyFrame. Every operation (row count, value options inference, page slicing) must use lazy queries that Polars can push down into the scan. If a full-dataset scan is unavoidable (e.g. counting rows on a format without metadata), it must be a streaming count — never materialise all rows into a DataFrame.
- **No eager full-dataset scans at init**: The `_infer_value_options` function must NOT scan the entire dataset upfront. Value options for filter dropdowns should be computed lazily — either deferred until the user actually opens a filter, or sampled, or skipped for large datasets. The grid must be usable within seconds even on multi-million-row files.
- **Always-visible filter buttons in column headers**: Every column header must have a clickable filter icon/button on the right side of the header text. Clicking it opens the filter panel for that column. These buttons must always be visible (not hidden behind a hover or menu). This is a core UX requirement — users must see at a glance that columns are filterable and be able to filter with one click.
- **Memory safety**: The grid must never hold more rows in memory (in `lf_grid_rows`) than what has been scrolled to. Each scroll chunk appends only the new slice. Filter/sort resets must clear accumulated rows and start fresh from offset 0.

## Coding Standards

- **Avoid nested try-catch**: try catch often just hide errors, put them only when errors is what we consider unavoidable in the use-case.
- **Type hints**: Mandatory for all Python code.
- **Pathlib**: Always use for all file paths.
- **No relative imports**: Always use absolute imports.
- **No placeholders**: Never use `/my/custom/path/` in code.
- **No legacy support**: Refactor aggressively; do not keep old API functions.
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
