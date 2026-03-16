"""Pydantic-style models for MUI X DataGrid column definitions and configuration."""

import typing
import json
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


class BadgeCellRenderer(rx.Var):
    """An ``rx.Var`` that renders a cell as a colored badge/pill.

    Inherits from ``rx.Var`` so it can be passed directly to
    ``ColumnDef.render_cell``.

    Args:
        color: CSS ``color`` applied to the text.
        bg_color: CSS ``backgroundColor`` applied to the badge.
        color_map: Dictionary mapping cell values to text colors.
            Overrides ``color`` if a match is found.
        bg_color_map: Dictionary mapping cell values to background colors.
            Overrides ``bg_color`` if a match is found.
        border_radius: CSS ``borderRadius`` for the badge (default ``"16px"``).
        padding: CSS ``padding`` for the badge (default ``"4px 8px"``).
    """

    def __new__(
        cls,
        color: str | None = None,
        bg_color: str | None = None,
        color_map: dict[Any, str] | None = None,
        bg_color_map: dict[Any, str] | None = None,
        border_radius: str = "16px",
        padding: str = "4px 8px",
    ) -> "BadgeCellRenderer":
        js_expr = f"""(params) => {{
            const val = params.value;
            const formattedVal = params.formattedValue || val;
            if (val == null) return '';
            
            let c = {repr(color) if color else "''"};
            let bg = {repr(bg_color) if bg_color else "''"};
            
            const colorMap = {json.dumps(color_map) if color_map else "{}"};
            const bgColorMap = {json.dumps(bg_color_map) if bg_color_map else "{}"};
            
            if (colorMap.hasOwnProperty(val)) c = colorMap[val];
            if (bgColorMap.hasOwnProperty(val)) bg = bgColorMap[val];
            
            return React.createElement('div', {{
                style: {{
                    color: c || 'inherit',
                    backgroundColor: bg || 'transparent',
                    borderRadius: '{border_radius}',
                    padding: '{padding}',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: '500',
                    fontSize: '0.85em',
                    lineHeight: '1.2',
                    minWidth: '24px',
                    textAlign: 'center'
                }}
            }}, formattedVal);
        }}"""
        instance = object.__new__(cls)
        object.__setattr__(instance, "_js_expr", js_expr)
        object.__setattr__(instance, "_var_type", typing.Any)
        object.__setattr__(instance, "_var_data", None)
        return instance  # type: ignore[return-value]

    def __init__(self, **kwargs) -> None:
        pass


class ProgressBarCellRenderer(rx.Var):
    """An ``rx.Var`` that renders a cell as a progress bar.

    Inherits from ``rx.Var`` so it can be passed directly to
    ``ColumnDef.render_cell``.
    """

    def __new__(
        cls,
        min_value: float = 0.0,
        max_value: float = 100.0,
        color: str = "#1976d2",
        track_color: str = "#e0e0e0",
        height: str = "8px",
        show_value: bool = True,
    ) -> "ProgressBarCellRenderer":
        js_expr = f"""(params) => {{
            const val = Number(params.value);
            if (isNaN(val)) return '';
            const min = {min_value};
            const max = {max_value};
            const percent = Math.max(0, Math.min(100, ((val - min) / (max - min)) * 100));
            const formattedVal = params.formattedValue || params.value;
            
            const bar = React.createElement('div', {{ style: {{ flex: 1, height: '{height}', backgroundColor: '{track_color}', borderRadius: '4px', overflow: 'hidden' }} }},
                React.createElement('div', {{ style: {{ width: `${{percent}}%`, height: '100%', backgroundColor: '{color}', borderRadius: '4px' }} }})
            );
            
            if (!{str(show_value).lower()}) {{
                return React.createElement('div', {{ style: {{ width: '100%', height: '100%', display: 'flex', alignItems: 'center' }} }}, bar);
            }}
            
            return React.createElement('div', {{
                style: {{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', gap: '8px' }}
            }}, 
                bar,
                React.createElement('span', {{ style: {{ fontSize: '0.85em', minWidth: '40px', textAlign: 'right' }} }}, formattedVal)
            );
        }}"""
        instance = object.__new__(cls)
        object.__setattr__(instance, "_js_expr", js_expr)
        object.__setattr__(instance, "_var_type", typing.Any)
        object.__setattr__(instance, "_var_data", None)
        return instance  # type: ignore[return-value]

    def __init__(self, **kwargs) -> None:
        pass


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
    type: (
        Literal["string", "number", "date", "dateTime", "boolean", "singleSelect"]
        | None
    ) = None
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
    cell_renderer_type: Literal["badge", "progress_bar", "url"] | None = None
    cell_renderer_config: dict[str, Any] | None = None
    disable_column_menu: bool | rx.Var[bool] = False
