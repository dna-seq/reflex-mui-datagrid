"""Grid query failures must stay isolated from the ASGI worker."""

from __future__ import annotations

import time

import pytest

from reflex_mui_datagrid.lazyframe_grid import (
    LazyFrameGridError,
    _run_grid_query,
)


def test_run_grid_query_returns_result() -> None:
    assert _run_grid_query(lambda: 42, label="test") == 42


def test_run_grid_query_timeout_becomes_lazyframe_grid_error() -> None:
    def _hang() -> int:
        time.sleep(2.0)
        return 1

    with pytest.raises(LazyFrameGridError, match="timed out"):
        _run_grid_query(_hang, label="hang test", timeout=0.05)


def test_run_grid_query_timeout_returns_without_awaiting_the_query() -> None:
    """A ``with``-scoped executor would shutdown(wait=True) and defeat the timeout."""

    def _hang() -> int:
        time.sleep(3.0)
        return 1

    start = time.perf_counter()
    with pytest.raises(LazyFrameGridError):
        _run_grid_query(_hang, label="hang test", timeout=0.1)
    assert time.perf_counter() - start < 1.0

    # The shared pool must still serve queries while the abandoned thread runs.
    assert _run_grid_query(lambda: "ok", label="after timeout") == "ok"


def test_run_grid_query_default_has_no_timeout_ceiling() -> None:
    """Huge LazyFrame sorts must not die at an arbitrary 60s default."""
    assert _run_grid_query(lambda: "ok", label="default") == "ok"
