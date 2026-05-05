"""Optional Plotly support for bell curve detail renderers.

Include ``PlotlyDetailSupport.create()`` in your component tree to
ensure ``react-plotly.js`` is installed in ``.web/node_modules/``.
This is only needed when using ``detail_renderers`` with
``type: "bell_curve"`` and you don't already use ``rx.plotly``
elsewhere in your app.

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
    """Invisible component that triggers ``react-plotly.js`` npm installation.

    Renders nothing — exists only to make Reflex install the npm packages.
    """

    library: str = "react-plotly.js@^2.6.0"
    tag: str = "_PlotlyNoop"
    is_default: bool = False
    lib_dependencies: list[str] = ["plotly.js-dist-min@^3.0.0"]

    @property
    def import_var(self) -> rx.ImportVar:
        return rx.ImportVar(tag=None, render=False)

    def add_custom_code(self) -> list[str]:
        return ["const _PlotlyNoop = () => null;"]
