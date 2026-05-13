"""Pydantic-style models for MUI X DataGrid column definitions and configuration."""

import typing
import json
from typing import Any, Literal

import reflex as rx
from pydantic import BaseModel
from reflex.components.props import PropsBase


# ---------------------------------------------------------------------------
# Detail renderer data models
# ---------------------------------------------------------------------------


class TonedItem(BaseModel):
    """A labeled item with an optional semantic tone for detail renderers.

    Used by ``key_value_list``, ``metric_list``, and ``badge_list``
    renderer types.

    Tones: ``"neutral"`` | ``"good"`` | ``"info"`` | ``"warning"`` | ``"danger"``
    (defaults to ``"neutral"`` on the JS side when omitted).
    """

    label: str
    value: str | float | None = None
    tone: Literal["neutral", "good", "info", "warning", "danger"] | None = None
    subtext: str | None = None


class PercentileData(BaseModel):
    """Structured data for ``percentile_spread`` and ``bell_curve`` renderers.

    The ``score`` field marks the user's position on the distribution.
    Each item in ``items`` is a labeled data point (e.g. a population or
    PGS model) plotted on the scale.

    Example::

        PercentileData(
            score=68.2,
            items=[
                TonedItem(label="EUR", value=68.2),
                TonedItem(label="EAS", value=45.1, tone="info"),
            ],
            outliers=["SAS"],
            summary="Models agree.",
        )
    """

    score: float | None = None
    items: list[TonedItem] = []
    outliers: list[str] = []
    summary: str = ""
    score_label: str | None = None


class PercentileBand(BaseModel):
    """A labeled range on the percentile scale.

    Rendered as a shaded region on ``percentile_spread`` / ``bell_curve``.
    """

    from_: float
    to: float
    label: str = ""

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        d = super().model_dump(**kwargs)
        d["from"] = d.pop("from_")
        return d


class DetailRendererConfig(BaseModel):
    """Configuration for a single detail renderer.

    Pass a dict of ``{field: DetailRendererConfig(...).model_dump()}`` to
    the ``detail_renderers`` prop, or just pass plain dicts -- the JS
    side accepts either.

    Example::

        detail_renderers={
            "risk_details": DetailRendererConfig(type="key_value_list").model_dump(),
            "population_percentiles": DetailRendererConfig(
                type="bell_curve",
                scale_min=0,
                scale_max=100,
                bands=[PercentileBand(from_=25, to=75, label="average range")],
            ).model_dump(),
        }
    """

    type: Literal[
        "text",
        "key_value_list",
        "metric_list",
        "badge_list",
        "link_list",
        "percentile_spread",
        "bell_curve",
    ]
    scale_min: float | None = None
    scale_max: float | None = None
    bands: list[PercentileBand] | None = None
    summary_placement: Literal["sidePanel", "fullWidth", "chart", "none"] | None = None
    height: int | None = None
    max_width: int | None = None
    side_panel_title: str | None = None
    show_side_panel: bool | None = None
    label_mode: Literal["auto", "always", "none"] | None = None
    label_max_visible: int | None = None
    label_min_gap_z: float | None = None
    label_tiers: int | None = None
    label_y_offset: int | None = None
    label_y_offset_step: int | None = None
    label_x_offset_step: int | None = None
    label_font_size: int | None = None
    score_label_font_size: int | None = None
    score_label_y_offset: int | None = None
    score_label_x_offset: int | None = None
    score_label_reserved_tiers: int | None = None
    score_label_color: str | None = None
    score_label_bg_color: str | None = None
    score_label_border_color: str | None = None
    score_label_border_pad: int | None = None
    margin_top: int | None = None
    margin_bottom: int | None = None
    legend_y: float | None = None
    x_title_standoff: int | None = None
    y_axis_max: float | None = None
    base_url: str | None = None
    suffix_url: str | None = None
    target: str | None = None

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        d = super().model_dump(exclude_none=True, **kwargs)
        if "scale_min" in d:
            d["scaleMin"] = d.pop("scale_min")
        if "scale_max" in d:
            d["scaleMax"] = d.pop("scale_max")
        if "summary_placement" in d:
            d["summaryPlacement"] = d.pop("summary_placement")
        if "max_width" in d:
            d["maxWidth"] = d.pop("max_width")
        if "side_panel_title" in d:
            d["sidePanelTitle"] = d.pop("side_panel_title")
        if "show_side_panel" in d:
            d["showSidePanel"] = d.pop("show_side_panel")
        if "label_mode" in d:
            d["labelMode"] = d.pop("label_mode")
        if "label_max_visible" in d:
            d["labelMaxVisible"] = d.pop("label_max_visible")
        if "label_min_gap_z" in d:
            d["labelMinGapZ"] = d.pop("label_min_gap_z")
        if "label_tiers" in d:
            d["labelTiers"] = d.pop("label_tiers")
        if "label_y_offset" in d:
            d["labelYOffset"] = d.pop("label_y_offset")
        if "label_y_offset_step" in d:
            d["labelYOffsetStep"] = d.pop("label_y_offset_step")
        if "label_x_offset_step" in d:
            d["labelXOffsetStep"] = d.pop("label_x_offset_step")
        if "label_font_size" in d:
            d["labelFontSize"] = d.pop("label_font_size")
        if "score_label_font_size" in d:
            d["scoreLabelFontSize"] = d.pop("score_label_font_size")
        if "score_label_y_offset" in d:
            d["scoreLabelYOffset"] = d.pop("score_label_y_offset")
        if "score_label_x_offset" in d:
            d["scoreLabelXOffset"] = d.pop("score_label_x_offset")
        if "score_label_reserved_tiers" in d:
            d["scoreLabelReservedTiers"] = d.pop("score_label_reserved_tiers")
        if "score_label_color" in d:
            d["scoreLabelColor"] = d.pop("score_label_color")
        if "score_label_bg_color" in d:
            d["scoreLabelBgColor"] = d.pop("score_label_bg_color")
        if "score_label_border_color" in d:
            d["scoreLabelBorderColor"] = d.pop("score_label_border_color")
        if "score_label_border_pad" in d:
            d["scoreLabelBorderPad"] = d.pop("score_label_border_pad")
        if "margin_top" in d:
            d["marginTop"] = d.pop("margin_top")
        if "margin_bottom" in d:
            d["marginBottom"] = d.pop("margin_bottom")
        if "legend_y" in d:
            d["legendY"] = d.pop("legend_y")
        if "x_title_standoff" in d:
            d["xTitleStandoff"] = d.pop("x_title_standoff")
        if "y_axis_max" in d:
            d["yAxisMax"] = d.pop("y_axis_max")
        if "base_url" in d:
            d["baseUrl"] = d.pop("base_url")
        if "suffix_url" in d:
            d["suffixUrl"] = d.pop("suffix_url")
        if "bands" in d:
            d["bands"] = [b.model_dump() for b in (self.bands or [])]
        return d


class UrlCellRenderer(rx.Var):
    """An ``rx.Var`` that renders a cell as a clickable ``<a>`` link.

    Inherits from ``rx.Var`` so it can be passed directly to
    ``ColumnDef.render_cell`` without any extra wrapping.

    Args:
        base_url: Optional URL prefix.  The cell value (``params.value``)
            is appended to form the full href.  Leave empty when the cell
            already contains the full URL.
        suffix_url: Optional URL suffix appended after the cell value.
            Useful for URLs like ``https://example.com/items/{value}/details``.
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
        suffix_url: str = "",
        label_field: str | None = None,
        target: str = "_blank",
        color: str = "inherit",
    ) -> "UrlCellRenderer":
        if base_url or suffix_url:
            href_expr = f"'{base_url}' + params.value + '{suffix_url}'"
        else:
            href_expr = "params.value"
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
        suffix_url: str = "",
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
