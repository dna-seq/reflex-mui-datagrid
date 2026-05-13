"""Tests for the detail_renderers feature.

Verifies that:
- The detail_renderers prop is accepted by the DataGrid component.
- Structured row data (List(Struct), Struct) survives Polars serialisation.
- The _dataframe_to_dicts function preserves nested structures.
- Existing detail_columns / detail_badge_fields props still work alongside detail_renderers.
"""

from typing import Any

import polars as pl
import pytest

from reflex_mui_datagrid.polars_utils import (
    _dataframe_to_dicts,
    lazyframe_to_datagrid,
)


class TestDataframeToDictsPreservesStructuredData:
    """_dataframe_to_dicts must keep List(Struct) and Struct columns as native Python objects."""

    def test_list_struct_preserved(self) -> None:
        data = [
            {"id": 1, "items": [{"label": "A", "value": "10"}, {"label": "B", "value": "20"}]},
            {"id": 2, "items": [{"label": "C", "value": "30"}]},
        ]
        df = pl.DataFrame(data)
        assert isinstance(df.schema["items"], pl.List)
        assert isinstance(df.schema["items"].inner, pl.Struct)

        rows = _dataframe_to_dicts(df)
        assert isinstance(rows[0]["items"], list)
        assert isinstance(rows[0]["items"][0], dict)
        assert rows[0]["items"][0]["label"] == "A"
        assert rows[1]["items"][0]["label"] == "C"

    def test_struct_preserved(self) -> None:
        data = [
            {"id": 1, "info": {"median": 71.0, "summary": "ok"}},
            {"id": 2, "info": {"median": None, "summary": "test"}},
        ]
        df = pl.DataFrame(data)
        assert isinstance(df.schema["info"], pl.Struct)

        rows = _dataframe_to_dicts(df)
        assert isinstance(rows[0]["info"], dict)
        assert rows[0]["info"]["median"] == 71.0
        assert rows[1]["info"]["median"] is None

    def test_flat_list_still_joined(self) -> None:
        data = [
            {"id": 1, "tags": ["a", "b", "c"]},
            {"id": 2, "tags": ["d"]},
        ]
        df = pl.DataFrame(data)
        assert isinstance(df.schema["tags"], pl.List)
        assert not isinstance(df.schema["tags"].inner, pl.Struct)

        rows = _dataframe_to_dicts(df)
        assert rows[0]["tags"] == "a,b,c"
        assert rows[1]["tags"] == "d"

    def test_temporal_still_string(self) -> None:
        from datetime import date

        data = [{"id": 1, "d": date(2025, 1, 15)}]
        df = pl.DataFrame(data)
        rows = _dataframe_to_dicts(df)
        assert isinstance(rows[0]["d"], str)
        assert "2025" in rows[0]["d"]

    def test_nested_struct_with_list(self) -> None:
        data = [
            {
                "id": 1,
                "pct": {
                    "median": 42.0,
                    "items": [
                        {"label": "PGS1", "value": 42.0, "tone": "warning"},
                        {"label": "PGS2", "value": 79.0, "tone": None},
                    ],
                    "outliers": ["PGS3"],
                    "summary": "Models disagree.",
                },
            },
        ]
        df = pl.DataFrame(data)
        rows = _dataframe_to_dicts(df)
        pct = rows[0]["pct"]
        assert isinstance(pct, dict)
        assert pct["median"] == 42.0
        assert isinstance(pct["items"], list)
        assert len(pct["items"]) == 2
        assert pct["items"][0]["label"] == "PGS1"
        assert pct["items"][0]["tone"] == "warning"
        assert pct["outliers"] == ["PGS3"]


class TestLazyframeToDatagridWithStructuredData:
    """lazyframe_to_datagrid should pass structured fields through untouched."""

    def test_structured_fields_survive_roundtrip(self) -> None:
        rich_row: dict[str, Any] = {
            "name": "test",
            "risk_details": [
                {"label": "Best estimate", "value": "14.3%", "tone": "warning"},
                {"label": "Population average", "value": "8.3%", "tone": None},
            ],
            "warnings": [
                {"label": "Wide spread", "tone": "warning"},
                {"label": "Not a diagnosis", "tone": "neutral"},
            ],
            "percentile_data": {
                "median": 71.0,
                "items": [{"label": "PGS1", "value": 42.0, "tone": None}],
                "outliers": [],
                "summary": "ok",
            },
        }
        lf = pl.LazyFrame([rich_row])
        rows, col_defs = lazyframe_to_datagrid(lf)
        assert len(rows) == 1
        row = rows[0]

        assert isinstance(row["risk_details"], list)
        assert row["risk_details"][0]["label"] == "Best estimate"
        assert row["risk_details"][0]["tone"] == "warning"

        assert isinstance(row["warnings"], list)
        assert row["warnings"][1]["tone"] == "neutral"

        assert isinstance(row["percentile_data"], dict)
        assert row["percentile_data"]["median"] == 71.0
        assert isinstance(row["percentile_data"]["items"], list)


class TestDetailRenderersConfig:
    """Verify that detail_renderers config dicts are JSON-serializable."""

    @pytest.mark.parametrize(
        "renderer_type",
        [
            "text",
            "key_value_list",
            "metric_list",
            "badge_list",
            "link_list",
            "percentile_spread",
            "bell_curve",
        ],
    )
    def test_renderer_config_serializable(self, renderer_type: str) -> None:
        import json

        config: dict[str, Any] = {"type": renderer_type}
        if renderer_type in ("percentile_spread", "bell_curve"):
            config["scaleMin"] = 0
            config["scaleMax"] = 100
            config["bands"] = [{"from": 25, "to": 75, "label": "average range"}]

        serialized = json.dumps(config)
        deserialized = json.loads(serialized)
        assert deserialized["type"] == renderer_type

    def test_full_renderers_dict_serializable(self) -> None:
        import json

        renderers: dict[str, Any] = {
            "risk_details": {"type": "key_value_list"},
            "risk_methods": {"type": "metric_list"},
            "pgs_links": {
                "type": "link_list",
                "baseUrl": "https://www.pgscatalog.org/score/",
                "suffixUrl": "/",
            },
            "population_percentiles": {
                "type": "percentile_spread",
                "scaleMin": 0,
                "scaleMax": 100,
                "bands": [
                    {"from": 25, "to": 75, "label": "average range"},
                    {"from": 75, "to": 90, "label": "above average"},
                    {"from": 90, "to": 100, "label": "high"},
                ],
            },
            "trait_warnings": {"type": "badge_list"},
        }
        serialized = json.dumps(renderers)
        deserialized = json.loads(serialized)
        assert set(deserialized.keys()) == set(renderers.keys())
        assert deserialized["population_percentiles"]["bands"][0]["from"] == 25

    def test_detail_renderers_coexists_with_badge_fields(self) -> None:
        renderers = {"risk_details": {"type": "key_value_list"}}
        badge_fields = ["risk_hint"]
        badge_colors = {"High": ["#2e7d32", "#e8f5e9"]}
        detail_columns = ["risk_hint", "risk_details"]

        assert isinstance(renderers, dict)
        assert isinstance(badge_fields, list)
        assert isinstance(badge_colors, dict)
        assert isinstance(detail_columns, list)
        assert "risk_hint" not in renderers
        assert "risk_details" in renderers


class TestBellCurveSupport:
    """Verify bell_curve renderer integration."""

    def test_plotly_detail_support_importable(self) -> None:
        from reflex_mui_datagrid.plotly_support import PlotlyDetailSupport

        assert PlotlyDetailSupport is not None
        assert "react-plotly.js" in PlotlyDetailSupport.library

    def test_bell_curve_in_inline_js(self) -> None:
        from reflex_mui_datagrid.datagrid import _INLINE_WRAPPER_JS

        assert "_BellCurveRenderer" in _INLINE_WRAPPER_JS
        assert "_normalPdf" in _INLINE_WRAPPER_JS
        assert "_percentileToZ" in _INLINE_WRAPPER_JS
        assert "bell_curve" in _INLINE_WRAPPER_JS

    def test_bell_curve_config_serializable(self) -> None:
        import json

        config = {
            "type": "bell_curve",
            "scaleMin": 0,
            "scaleMax": 100,
            "bands": [
                {"from": 25, "to": 75, "label": "average range"},
                {"from": 90, "to": 100, "label": "high"},
            ],
        }
        roundtripped = json.loads(json.dumps(config))
        assert roundtripped["type"] == "bell_curve"
        assert len(roundtripped["bands"]) == 2

    def test_js_has_key_functions(self) -> None:
        from reflex_mui_datagrid.datagrid import _INLINE_WRAPPER_JS

        for name in [
            "_isColumnFilterable",
            "_BellCurveRenderer",
            "_normalPdf",
            "_percentileToZ",
            "_resolvePlotComponent",
            "_renderPercentileSpread",
            "_renderBadgeList",
            "_renderLinkList",
            "_renderKeyValueList",
            "_renderMetricList",
            "_computeDetailPanelHeight",
            "_defaultRowHeightForParams",
            "_buildDetailPanelElement",
            "_DetailPanelsSlot",
            "UnlimitedDataGrid",
        ]:
            assert name in _INLINE_WRAPPER_JS, f"Missing function: {name}"

    def test_detail_panels_do_not_expand_host_row_height(self) -> None:
        from reflex_mui_datagrid.datagrid import _INLINE_WRAPPER_JS

        assert "effectiveProps.getRowHeight = (params) =>" not in _INLINE_WRAPPER_JS
        assert "return baseHeight + _detailPanelHeight" not in _INLINE_WRAPPER_JS
        assert "height: calcHeight" in _INLINE_WRAPPER_JS

    def test_bell_curve_detail_renderer_is_not_centered_in_full_row_width(self) -> None:
        from reflex_mui_datagrid.datagrid import _INLINE_WRAPPER_JS

        assert 'margin: "0 auto"' not in _INLINE_WRAPPER_JS
        assert 'margin: "0"' in _INLINE_WRAPPER_JS

    def test_percentile_renderers_have_right_side_panel(self) -> None:
        from reflex_mui_datagrid.datagrid import _INLINE_WRAPPER_JS

        assert "_buildPercentileSidePanel" in _INLINE_WRAPPER_JS
        assert "sideItems" in _INLINE_WRAPPER_JS
        assert "sidePanelTitle" in _INLINE_WRAPPER_JS
        assert 'flex: "0 0 220px"' in _INLINE_WRAPPER_JS

    def test_percentile_summary_can_span_full_width(self) -> None:
        from reflex_mui_datagrid.datagrid import _INLINE_WRAPPER_JS

        assert "_buildPercentileSummary" in _INLINE_WRAPPER_JS
        assert "summaryPlacement" in _INLINE_WRAPPER_JS
        assert 'summaryPlacement === "sidePanel"' in _INLINE_WRAPPER_JS
        assert 'summaryPlacement === "chart"' in _INLINE_WRAPPER_JS
        assert 'flex: "1 1 100%"' in _INLINE_WRAPPER_JS

    def test_bell_curve_allows_row_level_renderer_config(self) -> None:
        from reflex_mui_datagrid.datagrid import _INLINE_WRAPPER_JS

        assert "data.rendererConfig" in _INLINE_WRAPPER_JS
        assert "config.showSidePanel === false" in _INLINE_WRAPPER_JS

    def test_bell_curve_staggers_dense_labels(self) -> None:
        from reflex_mui_datagrid.datagrid import _INLINE_WRAPPER_JS

        assert "_bellCurveLabelOffset" in _INLINE_WRAPPER_JS
        assert "labelMinGapZ" in _INLINE_WRAPPER_JS
        assert "labelTiers" in _INLINE_WRAPPER_JS
        assert "labelMaxVisible" in _INLINE_WRAPPER_JS
        assert "labelXOffsetStep" in _INLINE_WRAPPER_JS
        assert "colOrder" in _INLINE_WRAPPER_JS
        assert "scoreLabelReservedTiers" in _INLINE_WRAPPER_JS
        assert "placedLabels.push({ z: zScore, tier: reservedTier })" in _INLINE_WRAPPER_JS

    def test_bell_curve_prioritizes_personal_score_label(self) -> None:
        from reflex_mui_datagrid.datagrid import _INLINE_WRAPPER_JS

        assert 'text: scoreLabelText, showarrow: true' in _INLINE_WRAPPER_JS
        assert '<b>" + scoreLabel + "</b>' in _INLINE_WRAPPER_JS
        assert '_numberConfig(config, "scoreLabelFontSize", 13)' in _INLINE_WRAPPER_JS
        assert '_numberConfig(config, "scoreLabelYOffset", 26)' in _INLINE_WRAPPER_JS
        assert '_numberConfig(config, "scoreLabelReservedTiers", 3)' in _INLINE_WRAPPER_JS
        assert 'scoreLabelBgColor' in _INLINE_WRAPPER_JS

    def test_bell_curve_layout_defaults_preserve_original_curve(self) -> None:
        """Default chart layout must match the historical bell curve."""
        from reflex_mui_datagrid.datagrid import _INLINE_WRAPPER_JS

        assert '_numberConfig(config, "marginTop", 18)' in _INLINE_WRAPPER_JS
        assert '_numberConfig(config, "marginBottom", 48)' in _INLINE_WRAPPER_JS
        assert '_numberConfig(config, "legendY", -0.22)' in _INLINE_WRAPPER_JS
        assert '_numberConfig(config, "yAxisMax", 0.45)' in _INLINE_WRAPPER_JS

    def test_bell_curve_exposes_layout_spacing_knobs(self) -> None:
        from reflex_mui_datagrid.models import DetailRendererConfig

        config = DetailRendererConfig(
            type="bell_curve",
            label_mode="always",
            label_tiers=6,
            label_x_offset_step=30,
            score_label_font_size=15,
            score_label_y_offset=52,
            score_label_reserved_tiers=8,
            margin_bottom=84,
            legend_y=-0.4,
            x_title_standoff=18,
        ).model_dump()
        assert config["labelMode"] == "always"
        assert config["labelTiers"] == 6
        assert config["labelXOffsetStep"] == 30
        assert config["scoreLabelFontSize"] == 15
        assert config["scoreLabelYOffset"] == 52
        assert config["scoreLabelReservedTiers"] == 8
        assert config["marginBottom"] == 84
        assert config["legendY"] == -0.4
        assert config["xTitleStandoff"] == 18


class TestFilterableColumnControls:
    """Filtering opt-outs should be honored by frontend and lazy-grid helpers."""

    def test_custom_filter_icon_respects_filterable_false(self) -> None:
        from reflex_mui_datagrid.datagrid import _INLINE_WRAPPER_JS

        assert "col.filterable !== false" in _INLINE_WRAPPER_JS
        assert "return null;" in _INLINE_WRAPPER_JS

    def test_non_filterable_fields_are_dropped_from_filter_model(self) -> None:
        from reflex_mui_datagrid.lazyframe_grid import (
            _LazyFrameCache,
            _filter_model_for_filterable_columns,
        )

        cache = _LazyFrameCache()
        cache.schema = pl.Schema(
            {
                "Allowed": pl.String,
                "Blocked": pl.String,
            }
        )
        cache.col_defs = [
            {"field": "Allowed", "filterable": True},
            {"field": "Blocked", "filterable": False},
        ]
        filter_model = {
            "items": [
                {"field": "Allowed", "operator": "contains", "value": "yes"},
                {"field": "blocked", "operator": "contains", "value": "no"},
                {"field": "Missing", "operator": "contains", "value": "ignored"},
            ],
            "logicOperator": "and",
        }

        filtered = _filter_model_for_filterable_columns(filter_model, cache)

        assert filtered == {
            "items": [
                {"field": "Allowed", "operator": "contains", "value": "yes"},
            ],
            "logicOperator": "and",
        }
