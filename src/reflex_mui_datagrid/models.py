"""Pydantic-style models for MUI X DataGrid column definitions and configuration."""

import typing
from typing import Any, Literal

import reflex as rx
from reflex.components.props import PropsBase


class UrlCellRenderer(rx.Var):
    """An ``rx.Var`` that renders a cell as a clickable ``<a>`` link.

    Inherits from ``rx.Var`` so it can be passed directly to
    ``ColumnDef.render_cell`` without any extra wrapping.

    Args:
        base_url: Optional URL prefix.  The cell value (``params.value``)
            is appended to form the full href.  Leave empty when the cell
            already contains the full URL.
        label_field: Name of another column in the row to use as the visible
            link text (accessed via ``params.row.<label_field>``).  When
            ``None`` (default) the cell value itself is shown.
        target: HTML ``target`` attribute for the anchor (default ``"_blank"``).
        color: CSS ``color`` applied to the anchor element (default
            ``"inherit"`` so the link blends with the row style).
    """

    def __new__(
        cls,
        base_url: str = "",
        label_field: str | None = None,
        target: str = "_blank",
        color: str = "inherit",
    ) -> "UrlCellRenderer":
        href_expr = f"'{base_url}' + params.value" if base_url else "params.value"
        label_expr = f"params.row.{label_field}" if label_field else "params.value"
        js_expr = (
            f"(params) => React.createElement('a', "
            f"{{href: {href_expr}, target: '{target}', rel: 'noopener noreferrer', "
            f"style: {{color: '{color}'}}}}, {label_expr})"
        )
        instance = object.__new__(cls)
        object.__setattr__(instance, "_js_expr", js_expr)
        object.__setattr__(instance, "_var_type", typing.Any)
        object.__setattr__(instance, "_var_data", None)
        return instance  # type: ignore[return-value]

    def __init__(
        self,
        base_url: str = "",
        label_field: str | None = None,
        target: str = "_blank",
        color: str = "inherit",
    ) -> None:
        pass  # all state set in __new__; frozen dataclass fields cannot be re-set


class ColumnDef(PropsBase):
    """Column definition for the MUI X DataGrid, maps to GridColDef.

    Attributes are automatically converted from snake_case to camelCase
    when serialized to JavaScript props via PropsBase.
    """

    field: str
    header_name: str | None = None
    width: int | None = None
    min_width: int | None = None
    max_width: int | None = None
    flex: int | None = None
    type: Literal["string", "number", "date", "dateTime", "boolean", "singleSelect"] | None = None
    align: Literal["left", "center", "right"] | None = None
    header_align: Literal["left", "center", "right"] | None = None
    editable: bool | rx.Var[bool] = False
    sortable: bool | rx.Var[bool] = True
    filterable: bool | rx.Var[bool] = True
    resizable: bool | rx.Var[bool] = True
    hide: bool | rx.Var[bool] = False
    description: str | None = None
    value_options: list[str] | None = None
    value_getter: rx.Var | None = None
    value_formatter: rx.Var | None = None
    cell_class_name: str | None = None
    render_cell: rx.Var | None = None
    disable_column_menu: bool | rx.Var[bool] = False
