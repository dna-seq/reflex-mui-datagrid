"""Optional compatibility component for bell curve detail renderers.

``DataGrid`` installs the frontend Plotly packages because the injected
wrapper contains the dynamic ``react-plotly.js`` import. This no-op
component is kept for users who already added it explicitly in their
component tree.

Example::

    rx.fragment(
        PlotlyDetailSupport.create(),
        data_grid(
            ...,
            detail_renderers={"pct": {"type": "bell_curve"}},
        ),
    )

If ``react-plotly.js`` is not available at runtime, the bell curve
renderer automatically falls back to the div-based percentile spread.
"""

import reflex as rx


class PlotlyDetailSupport(rx.Component):
    """Invisible compatibility component for explicit Plotly setup."""

    library: str = "react-plotly.js@^2.6.0"
    tag: str = "_PlotlyNoop"
    is_default: bool = False
    lib_dependencies: list[str] = ["plotly.js-dist-min@^3.0.0"]

    @property
    def import_var(self) -> rx.ImportVar:
        return rx.ImportVar(tag=None, render=False)

    def add_custom_code(self) -> list[str]:
        return ["const _PlotlyNoop = () => null;"]
