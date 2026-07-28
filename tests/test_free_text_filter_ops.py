"""Free-text filter operators must not promote columns to singleSelect."""

from __future__ import annotations

import inspect

from reflex_mui_datagrid.lazyframe_grid import (
    LazyFrameGridMixin,
    _FREE_TEXT_FILTER_OPERATORS,
)


def test_free_text_operators_cover_mui_string_ops() -> None:
    assert _FREE_TEXT_FILTER_OPERATORS == frozenset(
        {"contains", "equals", "startsWith", "endsWith"}
    )


def test_dropdown_operators_are_not_free_text() -> None:
    for op in ("is", "not", "isAnyOf", "isEmpty", "isNotEmpty"):
        assert op not in _FREE_TEXT_FILTER_OPERATORS


def test_filter_icon_handler_does_not_upgrade_column_type() -> None:
    """Filter-icon path must only warm cache — never assign singleSelect.

    Upgrading on icon click races the open filter panel and blanks the
    value editor (Organization Name contains \"Adair\").
    """
    src = inspect.getsource(LazyFrameGridMixin.handle_lf_grid_request_value_options)
    assert "self.lf_grid_columns" not in src
    assert '"type": "singleSelect"' not in src
    assert "_get_or_compute_value_options" in src
