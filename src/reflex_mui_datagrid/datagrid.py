"""Reflex wrapper for the MUI X DataGrid (v8) component."""

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
# DataGrid component
# ---------------------------------------------------------------------------

class DataGrid(rx.Component):
    """Reflex wrapper for the MUI X DataGrid (Community, v8).

    Requires a parent container with explicit dimensions.
    Use ``WrappedDataGrid`` (or the ``data_grid`` namespace callable) for
    a version that automatically wraps itself in a sized ``<div>``.
    """

    library: str = "@mui/x-data-grid@^8.27.0"
    tag: str = "DataGrid"

    lib_dependencies: list[str] = [
        "@mui/material@^7.0.0",
        "@emotion/react@^11.14.0",
        "@emotion/styled@^11.14.0",
    ]

    # ---- data ----
    rows: rx.Var[list[dict[str, Any]]]
    columns: rx.Var[list[dict[str, Any]]]

    # ---- display ----
    loading: rx.Var[bool]
    density: rx.Var[Literal["comfortable", "compact", "standard"]]
    row_height: rx.Var[int]
    column_header_height: rx.Var[int]
    show_toolbar: rx.Var[bool]

    # ---- selection ----
    checkbox_selection: rx.Var[bool]
    row_selection: rx.Var[bool]
    disable_row_selection_on_click: rx.Var[bool]

    # ---- pagination ----
    pagination_model: rx.Var[dict[str, int]]
    page_size_options: rx.Var[list[int]]
    auto_page_size: rx.Var[bool]
    hide_footer_pagination: rx.Var[bool]

    # ---- sorting ----
    sort_model: rx.Var[list[dict[str, Any]]]
    sorting_order: rx.Var[list[str | None]]

    # ---- filtering ----
    disable_column_filter: rx.Var[bool]
    filter_debounce_ms: rx.Var[int]

    # ---- column features ----
    column_visibility_model: rx.Var[dict[str, bool]]
    disable_column_selector: rx.Var[bool]
    disable_density_selector: rx.Var[bool]

    # ---- row identification ----
    # get_row_id is a JS callback – handled via create()
    # (see ``row_id_field`` convenience parameter below)

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
            ).to(rx.EventChain)
        return super().create(*children, **props)


# ---------------------------------------------------------------------------
# WrappedDataGrid – auto-sized container
# ---------------------------------------------------------------------------

class WrappedDataGrid(DataGrid):
    """DataGrid wrapped in a ``<div>`` with explicit width / height.

    MUI DataGrid requires a parent container with explicit dimensions.
    This variant pops ``width`` and ``height`` from the props and applies
    them to an outer ``<div>``.
    """

    @classmethod
    def create(cls, *children: rx.Component, **props: Any) -> rx.Component:
        width = props.pop("width", "100%")
        height = props.pop("height", "400px")
        virtual_scroll = props.pop("virtual_scroll", False)

        if virtual_scroll:
            # Hide pagination and set pageSize to 100 (the maximum
            # allowed by the Community edition).  The DataGrid's built-in
            # row virtualisation only puts visible rows in the DOM, so
            # scrolling stays smooth.  For datasets > 100 rows the
            # footer remains visible to allow page navigation unless
            # the caller explicitly hides it.
            props.setdefault("pagination_model", {"page": 0, "pageSize": 100})
            props.setdefault("page_size_options", [25, 50, 100])

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
