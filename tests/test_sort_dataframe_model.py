"""Granian-safe DataFrame sorting used by LazyFrameGridMixin."""

from __future__ import annotations

import polars as pl

from reflex_mui_datagrid.polars_utils import sort_dataframe_model


def test_sort_dataframe_model_asc_and_desc() -> None:
    df = pl.DataFrame(
        {
            "Gene": ["C", "A", "B"],
            "n": [3, 1, 2],
        }
    )
    asc = sort_dataframe_model(df, [{"field": "Gene", "sort": "asc"}])
    assert asc["Gene"].to_list() == ["A", "B", "C"]
    assert asc["n"].to_list() == [1, 2, 3]

    desc = sort_dataframe_model(df, [{"field": "Gene", "sort": "desc"}])
    assert desc["Gene"].to_list() == ["C", "B", "A"]
    assert desc["n"].to_list() == [3, 2, 1]


def test_sort_dataframe_model_multi_key_and_nulls_last() -> None:
    df = pl.DataFrame(
        {
            "Category": ["b", "a", "a", None],
            "Trait": ["z", "y", "x", "w"],
        }
    )
    out = sort_dataframe_model(
        df,
        [
            {"field": "Category", "sort": "asc"},
            {"field": "Trait", "sort": "asc"},
        ],
    )
    assert out["Category"].to_list() == ["a", "a", "b", None]
    assert out["Trait"].to_list() == ["x", "y", "z", "w"]


def test_sort_dataframe_model_case_insensitive_field() -> None:
    df = pl.DataFrame({"Gene": ["b", "a"]})
    out = sort_dataframe_model(df, [{"field": "gene", "sort": "asc"}])
    assert out["Gene"].to_list() == ["a", "b"]
