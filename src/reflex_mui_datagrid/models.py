"""Pydantic-style models for MUI X DataGrid column definitions and configuration."""

from typing import Any, Literal

import reflex as rx
from reflex.components.props import PropsBase


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
