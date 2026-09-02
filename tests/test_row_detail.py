"""Row-detail records are derived from the clicked row, not a field list."""

from __future__ import annotations

from reflex_mui_datagrid.lazyframe_grid import (
    _format_selected_value,
    _selected_row_fields,
)


def test_format_selected_value_is_generic() -> None:
    assert _format_selected_value(None) == "—"
    assert _format_selected_value("") == "—"
    assert _format_selected_value(True) == "true"
    assert _format_selected_value(["G", "T"]) == "G, T"
    assert _format_selected_value({"a": 1}) == '{"a": 1}'
    assert _format_selected_value("protective") == "protective"


def test_selected_row_fields_follow_the_row_keys() -> None:
    row = {
        "__row_id__": 7,
        "rsid": "rs1",
        "weight": 0.19,
        "note": None,
    }
    fields = _selected_row_fields(row, {"rsid": "dbSNP id"})
    assert [item["field"] for item in fields] == ["rsid", "weight", "note"]
    by_field = {item["field"]: item for item in fields}
    assert by_field["rsid"]["value"] == "rs1"
    assert by_field["rsid"]["description"] == "dbSNP id"
    assert by_field["weight"]["value"] == "0.19"
    assert by_field["note"]["value"] == "—"
    assert "__row_id__" not in by_field


def test_selected_row_fields_do_not_assume_module_columns() -> None:
    row = {"chrom": "1", "pos": 100}
    fields = _selected_row_fields(row)
    assert [item["field"] for item in fields] == ["chrom", "pos"]
    assert {item["field"] for item in fields}.isdisjoint({"state", "module", "rsid"})
