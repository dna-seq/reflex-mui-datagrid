"""Reflex wrapper for the MUI X DataGrid (v8) component.

The wrapper code (``UnlimitedDataGrid``) is injected directly into Reflex's
compiled pages via ``add_imports()`` + ``add_custom_code()``.  This ensures
that the bare ``@mui/x-data-grid`` import resolves from ``.web/node_modules/``
even when the package is pip-installed into another project.

The ``enhanceColumnsWithDescriptions`` helper renders column descriptions
in a two-line header when ``showDescriptionInHeader`` is enabled.

Row virtualisation (only visible DOM rows are rendered) is built into
the Community edition and works regardless of page size, so scrolling
through thousands of rows stays smooth.
"""

from typing import Any, Literal

import reflex as rx
from reflex.components.el import Div

from reflex_mui_datagrid.models import ColumnDef


# ---------------------------------------------------------------------------
# Event-handler argument helpers
# ---------------------------------------------------------------------------
# MUI DataGrid callback objects contain non-serializable references (api,
# column objects, DOM nodes, etc.). The helpers below create small arrow-function
# wrappers that strip those keys before the value is sent to the Python backend.

def _js_strip_keys(event_var: str, exclude_keys: list[str]) -> str:
    """Return JS expression that destructures *exclude_keys* away from *event_var*."""
    keys = ", ".join(exclude_keys)
    return f"let {{{keys}, ...rest}} = {event_var}; return rest"


def _arrow_callback(js_body: str) -> rx.Var:
    """Wrap *js_body* in an immediately-invoked arrow function."""
    return rx.Var(f"(() => {{{js_body}}})()")


# -- Row click: strip api, columns object, node, event, etc.
def _on_row_click_spec(event: rx.Var) -> list[rx.Var]:
    exclude = ["api", "columns", "node", "event"]
    return [_arrow_callback(_js_strip_keys(str(event), exclude))]


# -- Cell click: strip heavy objects, keep id / field / value / row
def _on_cell_click_spec(event: rx.Var) -> list[rx.Var]:
    exclude = ["api", "colDef", "node", "event", "column"]
    return [_arrow_callback(_js_strip_keys(str(event), exclude))]


# -- Sort model change: the first arg is already a plain array
def _on_sort_model_change_spec(model: rx.Var) -> list[rx.Var]:
    return [model]


# -- Filter model change: the first arg is already a plain object
def _on_filter_model_change_spec(model: rx.Var) -> list[rx.Var]:
    return [model]


# -- Pagination model change: plain { page, pageSize } object
def _on_pagination_model_change_spec(model: rx.Var) -> list[rx.Var]:
    return [model]


# -- Row selection model change (v8):
#    v8 passes { type: 'include'|'exclude', ids: Set<GridRowId> }.
#    We convert the Set to an Array for JSON serialisation to Python.
def _on_row_selection_model_change_spec(model: rx.Var) -> list[rx.Var]:
    return [
        rx.Var(
            f"(() => {{ const m = {model}; return {{ type: m.type, ids: Array.from(m.ids) }} }})()"
        )
    ]


# -- Column visibility model change: plain { [field]: bool } dict
def _on_column_visibility_model_change_spec(model: rx.Var) -> list[rx.Var]:
    return [model]


# ---------------------------------------------------------------------------
# Inline JS wrapper – injected into compiled pages via add_custom_code().
#
# This defines the UnlimitedDataGrid component using MuiDataGrid_ (which is
# imported via add_imports as an alias for the real MUI DataGrid).
# The wrapper adds the enhanceColumnsWithDescriptions feature.
#
# Note: The CJS monkey-patches from UnlimitedDataGrid.js (removing the
# 100-row cap and forcing pagination) rely on CommonJS require() which is
# unavailable in Vite's ESM environment, so they were already non-functional
# when served via Vite.  They are intentionally omitted here.
# ---------------------------------------------------------------------------
_INLINE_WRAPPER_JS = """
function _enhanceColumnsWithDescriptions(columns, showDescriptionInHeader) {
  if (!showDescriptionInHeader || !Array.isArray(columns)) return columns;
  return columns.map((col) => {
    if (!col.description || col.renderHeader) return col;
    const headerName = col.headerName || col.field;
    const desc = col.description;
    return {
      ...col,
      renderHeader: () =>
        React.createElement(
          "div",
          { style: { lineHeight: 1.2, overflow: "hidden", width: "100%" } },
          React.createElement(
            "div",
            { style: { fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" } },
            headerName
          ),
          React.createElement(
            "div",
            { style: { fontSize: "0.7em", color: "#888", fontWeight: 400, whiteSpace: "normal", lineHeight: 1.3, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" } },
            desc
          )
        ),
    };
  });
}
const UnlimitedDataGrid = React.forwardRef((props, ref) => {
  const { showDescriptionInHeader, columns, ...rest } = props;
  const enhancedColumns = _enhanceColumnsWithDescriptions(
    columns,
    showDescriptionInHeader
  );
  return React.createElement(MuiDataGrid_, {
    ...rest,
    columns: enhancedColumns,
    ref,
  });
});
UnlimitedDataGrid.displayName = "UnlimitedDataGrid";
"""


# ---------------------------------------------------------------------------
# DataGrid component
# ---------------------------------------------------------------------------

class DataGrid(rx.Component):
    """Reflex wrapper for the MUI X DataGrid (Community, v8).

    The 100-row page-size limit of the Community edition is removed via
    a small JS wrapper (see module docstring).  You can now set any
    ``pageSize`` or pass ``pagination=False`` to disable pagination
    entirely and let the user scroll through all rows.

    Requires a parent container with explicit dimensions.
    Use ``WrappedDataGrid`` (or the ``data_grid`` namespace callable) for
    a version that automatically wraps itself in a sized ``<div>``.
    """

    library: str = "@mui/x-data-grid"
    tag: str = "UnlimitedDataGrid"
    is_default: bool = False

    lib_dependencies: list[str] = [
        "@mui/material@^7.0.0",
        "@emotion/react@^11.14.0",
        "@emotion/styled@^11.14.0",
    ]

    @property
    def import_var(self) -> rx.ImportVar:
        """Override: install the npm package but do NOT emit an import for the tag.

        ``UnlimitedDataGrid`` does not exist in ``@mui/x-data-grid`` -- it is
        defined by ``add_custom_code()``.  Returning ``render=False`` tells
        Reflex to install the package without generating a broken import.
        """
        return rx.ImportVar(tag=None, render=False)

    def add_imports(self) -> dict:
        """Import DataGrid (aliased) and React (for createElement/forwardRef in the wrapper)."""
        return {
            "@mui/x-data-grid": [rx.ImportVar(tag="DataGrid", alias="MuiDataGrid_")],
            "react": [rx.ImportVar(tag="React", is_default=True)],
        }

    def add_custom_code(self) -> list[str]:
        """Inject the UnlimitedDataGrid wrapper component into the compiled page."""
        return [_INLINE_WRAPPER_JS]

    # ---- data ----
    rows: rx.Var[list[dict[str, Any]]]
    columns: rx.Var[list[dict[str, Any]]]

    # ---- display ----
    loading: rx.Var[bool]
    density: rx.Var[Literal["comfortable", "compact", "standard"]]
    row_height: rx.Var[int]
    column_header_height: rx.Var[int]
    show_toolbar: rx.Var[bool]
    show_description_in_header: rx.Var[bool]
    autosize_on_mount: rx.Var[bool]
    autosize_options: rx.Var[dict[str, Any]]

    # ---- selection ----
    checkbox_selection: rx.Var[bool]
    row_selection: rx.Var[bool]
    disable_row_selection_on_click: rx.Var[bool]

    # ---- pagination ----
    pagination: rx.Var[bool]
    pagination_model: rx.Var[dict[str, int]]
    page_size_options: rx.Var[list[int]]
    auto_page_size: rx.Var[bool]
    hide_footer_pagination: rx.Var[bool]
    hide_footer: rx.Var[bool]

    # ---- sorting ----
    sort_model: rx.Var[list[dict[str, Any]]]
    sorting_order: rx.Var[list[str | None]]

    # ---- filtering ----
    disable_column_filter: rx.Var[bool]
    filter_debounce_ms: rx.Var[int]
    filter_model: rx.Var[dict[str, Any]]

    # ---- column features ----
    column_visibility_model: rx.Var[dict[str, bool]]
    column_grouping_model: rx.Var[list[dict[str, Any]]]
    disable_column_selector: rx.Var[bool]
    disable_density_selector: rx.Var[bool]

    # ---- slots / customisation ----
    slot_props: rx.Var[dict[str, Any]]

    # ---- row identification ----
    get_row_id: rx.Var[Any]

    # ---- event handlers ----
    on_row_click: rx.EventHandler[_on_row_click_spec]
    on_cell_click: rx.EventHandler[_on_cell_click_spec]
    on_sort_model_change: rx.EventHandler[_on_sort_model_change_spec]
    on_filter_model_change: rx.EventHandler[_on_filter_model_change_spec]
    on_pagination_model_change: rx.EventHandler[_on_pagination_model_change_spec]
    on_row_selection_model_change: rx.EventHandler[_on_row_selection_model_change_spec]
    on_column_visibility_model_change: rx.EventHandler[_on_column_visibility_model_change_spec]

    @classmethod
    def create(
        cls,
        *children: rx.Component,
        row_id_field: str | None = None,
        **props: Any,
    ) -> rx.Component:
        """Create a DataGrid component.

        Args:
            *children: Child components (typically unused).
            row_id_field: Convenience shortcut – if provided, a JS ``getRowId``
                callback is generated that reads the given field from each row
                object.  Equivalent to ``getRowId={(row) => row.<field>}``.
            **props: All other DataGrid props.

        Returns:
            The DataGrid component.
        """
        if row_id_field is not None:
            props["get_row_id"] = rx.Var(
                f"(row) => row.{row_id_field}"
            )
        return super().create(*children, **props)


# ---------------------------------------------------------------------------
# WrappedDataGrid – auto-sized container
# ---------------------------------------------------------------------------

class WrappedDataGrid(DataGrid):
    """DataGrid wrapped in a ``<div>`` with explicit width / height.

    MUI DataGrid requires a parent container with explicit dimensions.
    This variant pops ``width`` and ``height`` from the props and applies
    them to an outer ``<div>``.

    Pagination is **off** by default – all rows are scrollable via
    MUI's built-in row virtualisation (only visible DOM rows are
    rendered).  Pass ``pagination=True`` to re-enable pagination.
    """

    @classmethod
    def create(cls, *children: rx.Component, **props: Any) -> rx.Component:
        width = props.pop("width", "100%")
        height = props.pop("height", "400px")
        # ``virtual_scroll`` is kept as an alias for backwards compat
        # but is no longer needed – pagination is off by default.
        props.pop("virtual_scroll", None)

        # Default: no pagination, no footer, autosize columns.
        props.setdefault("pagination", False)
        props.setdefault("hide_footer", True)
        props.setdefault("autosize_on_mount", True)
        props.setdefault("autosize_options", {
            "includeHeaders": True,
            "includeOutliers": True,
            "expand": True,
        })

        # Position the filter/preferences panel below the headers so it
        # does not obscure column titles.
        props.setdefault("slot_props", {
            "panel": {
                "placement": "bottom-end",
            },
        })

        return Div.create(
            super().create(*children, **props),
            width=width,
            height=height,
        )


# ---------------------------------------------------------------------------
# Namespace (so users can write ``data_grid(...)`` and ``data_grid.column_def``)
# ---------------------------------------------------------------------------

class DataGridNamespace(rx.ComponentNamespace):
    """Namespace for the MUI DataGrid component family."""

    column_def = ColumnDef
    root = DataGrid.create
    __call__ = WrappedDataGrid.create


data_grid = DataGridNamespace()
