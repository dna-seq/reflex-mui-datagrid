"""Reflex wrapper for the MUI X DataGrid (v8) component.

The wrapper code (``UnlimitedDataGrid``) is injected directly into Reflex's
compiled pages via ``add_imports()`` + ``add_custom_code()``.  This ensures
that the bare ``@mui/x-data-grid`` import resolves from ``.web/node_modules/``
even when the package is pip-installed into another project.

The ``enhanceColumnsWithDescriptions`` helper renders column descriptions
in a two-line header when ``showDescriptionInHeader`` is enabled.

Row virtualisation (only visible DOM rows are rendered) is built into
the Community edition and works regardless of page size, so scrolling
through thousands of rows stays smooth.
"""

from typing import Any, Literal

import reflex as rx
from reflex.components.el import Div

from reflex_mui_datagrid.models import ColumnDef


# ---------------------------------------------------------------------------
# Event-handler argument helpers
# ---------------------------------------------------------------------------
# MUI DataGrid callback objects contain non-serializable references (api,
# column objects, DOM nodes, etc.). The helpers below create small arrow-function
# wrappers that strip those keys before the value is sent to the Python backend.

def _js_strip_keys(event_var: str, exclude_keys: list[str]) -> str:
    """Return JS expression that destructures *exclude_keys* away from *event_var*."""
    keys = ", ".join(exclude_keys)
    return f"let {{{keys}, ...rest}} = {event_var}; return rest"


def _arrow_callback(js_body: str) -> rx.Var:
    """Wrap *js_body* in an immediately-invoked arrow function."""
    return rx.Var(f"(() => {{{js_body}}})()")


# -- Row click: strip api, columns object, node, event, etc.
def _on_row_click_spec(event: rx.Var) -> list[rx.Var]:
    exclude = ["api", "columns", "node", "event"]
    return [_arrow_callback(_js_strip_keys(str(event), exclude))]


# -- Cell click: strip heavy objects, keep id / field / value / row
def _on_cell_click_spec(event: rx.Var) -> list[rx.Var]:
    exclude = ["api", "colDef", "node", "event", "column"]
    return [_arrow_callback(_js_strip_keys(str(event), exclude))]


# -- Sort model change: the first arg is already a plain array
def _on_sort_model_change_spec(model: rx.Var) -> list[rx.Var]:
    return [model]


# -- Filter model change: the first arg is already a plain object
def _on_filter_model_change_spec(model: rx.Var) -> list[rx.Var]:
    return [model]


# -- Pagination model change: plain { page, pageSize } object
def _on_pagination_model_change_spec(model: rx.Var) -> list[rx.Var]:
    return [model]


# -- Row selection model change (v8):
#    v8 passes { type: 'include'|'exclude', ids: Set<GridRowId> }.
#    We convert the Set to an Array for JSON serialisation to Python.
def _on_row_selection_model_change_spec(model: rx.Var) -> list[rx.Var]:
    return [
        rx.Var(
            f"(() => {{ const m = {model}; return {{ type: m.type, ids: Array.from(m.ids) }} }})()"
        )
    ]


# -- Column visibility model change: plain { [field]: bool } dict
def _on_column_visibility_model_change_spec(model: rx.Var) -> list[rx.Var]:
    return [model]


# -- Virtual-scroll near-end callback payload (scroll metrics)
def _on_rows_scroll_end_spec(event: rx.Var) -> list[rx.Var]:
    return [event]


# -- Request value options for a column (field name string)
def _on_request_value_options_spec(field: rx.Var) -> list[rx.Var]:
    return [field]


# ---------------------------------------------------------------------------
# Inline JS wrapper – injected into compiled pages via add_custom_code().
#
# This defines the UnlimitedDataGrid component using MuiDataGrid_ (which is
# imported via add_imports as an alias for the real MUI DataGrid).
#
# ESM-compatible monkey-patching (Vite / Rolldown):
#
# The MUI DataGrid Community edition enforces two restrictions:
#   1. ``pagination`` is forced to ``true`` via ``DATA_GRID_FORCED_PROPS``.
#   2. ``pageSize > 100`` triggers ``throwIfPageSizeExceedsTheLimit``.
#
# Both checks compare against ``GridSignature.DataGrid``, a property on
# a plain JS object.  Crucially, ``GridSignature`` is exported from the
# *same* npm entry point (``@mui/x-data-grid``) as ``DataGrid``, so
# after Vite pre-bundles them into a single file they share the exact
# same object reference.  Mutating ``GridSignature.DataGrid`` at module
# load time makes *all* internal comparisons
# ``signatureProp === GridSignature.DataGrid`` fail, because the forced
# prop still uses the original string literal ``'DataGrid'``.
#
# For ``pagination=false`` (continuous scrolling with a vertical scrollbar):
# MUI still forces ``pagination=true`` internally, so the wrapper sets
# ``pageSize`` to the total row count and hides the footer, putting all
# rows on a single "page".  MUI's built-in row virtualisation then
# renders only the visible DOM rows, and the virtual scroller shows a
# vertical scrollbar.
#
# A lightweight React Error Boundary (``_DataGridGuard``) provides a
# graceful fallback: if the patch did not propagate for any reason, the
# guard catches the ``pageSize > 100`` error and re-renders the grid in
# safe paginated (``autoPageSize``) mode instead of crashing the page.
# ---------------------------------------------------------------------------
_INLINE_WRAPPER_JS = """
// ---------------------------------------------------------------------------
// 1. Patch: Bypass MUI DataGrid Community 100-row page-size limit.
//
// GridSignature_ is imported from the *same* @mui/x-data-grid entry
// point as MuiDataGrid_, so Vite pre-bundles them into one file and
// they share the same object reference.  Mutating the .DataGrid
// property makes all internal `signatureProp === GridSignature.DataGrid`
// comparisons evaluate to false, removing the cap.
// ---------------------------------------------------------------------------
let _muiPatchActive = false;
try {
  if (typeof GridSignature_ !== 'undefined' && GridSignature_ &&
      GridSignature_.DataGrid === 'DataGrid') {
    GridSignature_.DataGrid = 'DataGrid_Unlimited';
    _muiPatchActive = true;
  }
} catch (_e) { /* import unavailable — handled by Error Boundary */ }

// ---------------------------------------------------------------------------
// 2. Error Boundary: graceful degradation when the patch does not take
//    effect (e.g. future MUI version removes GridSignature export).
//    Catches the "pageSize > 100" error and re-renders in safe mode.
// ---------------------------------------------------------------------------
class _DataGridGuard extends React.Component {
  constructor(props) {
    super(props);
    this.state = { pageSizeError: false, otherError: null };
  }
  static getDerivedStateFromError(error) {
    if (error && typeof error.message === 'string' &&
        error.message.indexOf('pageSize') !== -1 &&
        error.message.indexOf('100') !== -1) {
      return { pageSizeError: true, otherError: null };
    }
    return { pageSizeError: false, otherError: error };
  }
  componentDidCatch(error) {
    if (this.state.pageSizeError) {
      console.warn(
        '[reflex-mui-datagrid] GridSignature patch did not propagate. ' +
        'Falling back to paginated mode (autoPageSize).'
      );
    }
  }
  render() {
    if (this.state.otherError) throw this.state.otherError;
    if (this.state.pageSizeError && typeof this.props.fallback === 'function') {
      return this.props.fallback();
    }
    return this.props.children;
  }
}

// ---------------------------------------------------------------------------
// 3. Column-description header enhancer
//
// When a column has a `description`, renderHeader produces a two-line header
// (bold name + smaller description).  The ref callback walks up to the
// MUI-internal `columnHeaderTitleContainerContent` wrapper and forces
// `flex: 1 1 auto` so the title block always fills remaining space and
// pushes sort/filter icons to the right edge of the column.
// ---------------------------------------------------------------------------
function _forceParentFlex(el) {
  if (!el) return;
  const parent = el.parentElement;
  if (parent && parent.classList.contains("MuiDataGrid-columnHeaderTitleContainerContent")) {
    parent.style.flex = "1 1 auto";
    parent.style.minWidth = "0";
    parent.style.overflow = "hidden";
  }
}

function _enhanceColumnsWithDescriptions(columns, showDescriptionInHeader) {
  if (!showDescriptionInHeader || !Array.isArray(columns)) return columns;
  return columns.map((col) => {
    if (!col.description || col.renderHeader) return col;
    const headerName = col.headerName || col.field;
    const desc = col.description;
    return {
      ...col,
      renderHeader: () =>
        React.createElement(
          "div",
          { ref: _forceParentFlex, style: { lineHeight: 1.2, overflow: "hidden", width: "100%" } },
          React.createElement(
            "div",
            { style: { fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" } },
            headerName
          ),
          React.createElement(
            "div",
            { style: { fontSize: "0.7em", color: "#888", fontWeight: 400, whiteSpace: "normal", lineHeight: 1.3, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" } },
            desc
          )
        ),
    };
  });
}

// ---------------------------------------------------------------------------
// 4. Debug logger – opt-in via debugLog={true} prop.
//    Logs to browser console with [DataGrid] prefix and timing info.
// ---------------------------------------------------------------------------
const _dgLog = (() => {
  let _seq = 0;
  return (enabled, ...args) => {
    if (!enabled) return;
    _seq++;
    console.log(
      `%c[DataGrid #${_seq}] %c${new Date().toISOString()}`,
      "color:#2196f3;font-weight:bold",
      "color:#999",
      ...args
    );
  };
})();

// ---------------------------------------------------------------------------
// 5. Custom filter panel with Apply button for server-side filtering.
//
// When filterMode="server", every keystroke in the filter value input
// triggers onFilterModelChange, which runs an expensive server query.
// This wrapper renders the standard GridFilterPanel and adds Apply/Reset
// buttons below it.  It intercepts onFilterModelChange at the grid level:
// changes are captured locally and only forwarded to the Python backend
// when the user clicks Apply (or presses Enter).
// ---------------------------------------------------------------------------
const _FilterPanelWithApply = React.forwardRef((props, ref) => {
  const apiRef = useGridApiContext_();

  // Apply: send the current grid filter model to the server.
  const handleApply = React.useCallback(() => {
    const currentModel = apiRef.current.state.filter.filterModel;
    // Dispatch a custom event that the UnlimitedDataGrid wrapper listens for.
    const event = new CustomEvent("_applyFilter", { detail: currentModel, bubbles: true });
    const el = apiRef.current.rootElementRef?.current;
    if (el) el.dispatchEvent(event);
  }, [apiRef]);

  // Reset: clear all filters and notify the server.
  const handleReset = React.useCallback(() => {
    const emptyModel = { items: [] };
    apiRef.current.setFilterModel(emptyModel);
    const event = new CustomEvent("_applyFilter", { detail: emptyModel, bubbles: true });
    const el = apiRef.current.rootElementRef?.current;
    if (el) el.dispatchEvent(event);
  }, [apiRef]);

  // Apply on Enter key press anywhere in the panel.
  const handleKeyDown = React.useCallback((event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      event.stopPropagation();
      handleApply();
    }
  }, [handleApply]);

  return React.createElement(
    "div",
    {
      onKeyDown: handleKeyDown,
      style: { display: "flex", flexDirection: "column" },
    },
    React.createElement(GridFilterPanel_, { ...props, ref: ref }),
    React.createElement(
      "div",
      {
        style: {
          display: "flex",
          justifyContent: "flex-end",
          gap: "8px",
          padding: "8px 16px 12px",
          borderTop: "1px solid rgba(0,0,0,0.12)",
        },
      },
      React.createElement(
        "button",
        {
          onClick: handleReset,
          style: {
            padding: "6px 16px",
            border: "1px solid rgba(0,0,0,0.23)",
            borderRadius: "4px",
            background: "transparent",
            cursor: "pointer",
            fontSize: "0.8125rem",
            fontFamily: "inherit",
            color: "inherit",
          },
        },
        "Reset"
      ),
      React.createElement(
        "button",
        {
          onClick: handleApply,
          style: {
            padding: "6px 16px",
            border: "none",
            borderRadius: "4px",
            background: "#1976d2",
            color: "#fff",
            cursor: "pointer",
            fontSize: "0.8125rem",
            fontFamily: "inherit",
            fontWeight: 500,
          },
        },
        "Apply"
      )
    )
  );
});
_FilterPanelWithApply.displayName = "_FilterPanelWithApply";

// ---------------------------------------------------------------------------
// 6. Prop builder – shared between the primary and fallback render paths.
// ---------------------------------------------------------------------------
// MUI's default header filter button opens a generic filter panel from header
// context. For always-visible filter icons, we use a custom button that opens
// the filter panel pre-targeted to the clicked column.
const _AlwaysVisibleFilterIconButton = (props) => {
  const { field, onClick } = props;
  const apiRef = useGridApiContext_();
  const rootProps = useGridRootProps_();

  // Detect whether this column has an active server-side filter.
  // activeFilterFields is a list of field names with accumulated
  // server-side filters (passed from the Python state).
  const activeFields = rootProps.activeFilterFields || rootProps.active_filter_fields;
  const hasActiveFilter = React.useMemo(() => {
    if (!Array.isArray(activeFields)) return false;
    return activeFields.includes(field);
  }, [activeFields, field]);

  const handleClick = React.useCallback((event) => {
    event.preventDefault();
    event.stopPropagation();
    // Request value options from the server before opening the panel.
    // The UnlimitedDataGrid wrapper listens for this event and calls
    // the Python handler, which may upgrade the column to singleSelect.
    const el = apiRef.current.rootElementRef?.current;
    if (el) {
      el.dispatchEvent(new CustomEvent("_requestValueOptions", {
        detail: field, bubbles: true,
      }));
    }
    apiRef.current.showFilterPanel(field);
    if (typeof onClick === "function") {
      onClick(apiRef.current.getColumnHeaderParams(field), event);
    }
  }, [apiRef, field, onClick]);

  // Active filter: blue icon; inactive: default grey.
  const iconColor = hasActiveFilter ? "#1976d2" : undefined;
  const iconStyle = hasActiveFilter
    ? { color: iconColor, filter: "drop-shadow(0 0 2px rgba(25,118,210,0.4))" }
    : {};

  const iconButton = React.createElement(
    rootProps.slots.baseIconButton,
    {
      onClick: handleClick,
      "aria-label": apiRef.current.getLocaleText("columnHeaderFiltersLabel"),
      size: "small",
      tabIndex: -1,
      "aria-haspopup": "menu",
      style: iconStyle,
      ...(rootProps.slotProps?.baseIconButton || {}),
    },
    React.createElement(rootProps.slots.columnFilteredIcon, {
      fontSize: "small",
      style: iconStyle,
    })
  );

  const tooltipTitle = hasActiveFilter
    ? apiRef.current.getLocaleText("columnMenuFilter") + " (active)"
    : apiRef.current.getLocaleText("columnMenuFilter");

  return React.createElement(
    rootProps.slots.baseTooltip,
    {
      title: tooltipTitle,
      enterDelay: 1000,
      ...(rootProps.slotProps?.baseTooltip || {}),
    },
    iconButton
  );
};

function _buildGridProps(props, unlimitedMode) {
  const {
    showDescriptionInHeader,
    columns,
    pagination,
    onRowsScrollEnd,
    scrollEndThreshold,
    debugLog,
    always_show_filter_icon,
    alwaysShowFilterIcon,
    onRequestValueOptions,
    ...rest
  } = props;
  // Widen columns so the header title is not hidden when MUI shows
  // sort/filter/menu icons on hover.  The icons need ~66px of space
  // (sort arrow ~20px + filter icon ~20px + menu dots ~26px).
  // We bump each column's minWidth to ensure the title always has room.
  const _ICON_SPACE = 66;
  const widenedColumns = (Array.isArray(columns) ? columns : []).map((col) => {
    const current = col.minWidth || 0;
    const needed = (col.width || 100) + _ICON_SPACE;
    return current >= needed ? col : { ...col, minWidth: Math.max(current, needed) };
  });
  const enhancedColumns = _enhanceColumnsWithDescriptions(
    widenedColumns, showDescriptionInHeader
  );
  const ep = { ...rest, columns: enhancedColumns };

  // Fix icon ordering in column headers.
  // MUI's columnHeaderTitleContainer is a flex row.  Its children vary:
  //   - .MuiDataGrid-columnHeaderTitle (default) OR custom renderHeader output
  //   - .MuiDataGrid-iconButtonContainer (sort arrow – only when column is sorted)
  //   - our custom columnHeaderFilterIconButton slot (always visible)
  // The sort icon appearing/disappearing causes the filter icon to shift.
  //
  // Fix: use CSS flexbox `order` to enforce a stable layout:
  //   [title: order 0, flex-grow] [sort: order 1, fixed 28px] [filter: order 2, fixed 28px]
  // The menu icon (.MuiDataGrid-menuIcon) is a sibling of titleContainer.
  const headerIconSx = {
    "& .MuiDataGrid-columnHeader": {
      "& .MuiDataGrid-columnHeaderTitleContainer": {
        display: "flex",
        alignItems: "center",
        flexWrap: "nowrap",
        overflow: "hidden",
      },
      // Sort icon: fixed slot, always reserves 28px even when hidden
      "& .MuiDataGrid-iconButtonContainer": {
        order: 1,
        display: "inline-flex",
        boxSizing: "border-box",
        width: 28,
        minWidth: 28,
        flexShrink: 0,
        justifyContent: "center",
        visibility: "visible",
      },
      // Filter icon (our always-visible slot): fixed 28px, rightmost in titleContainer
      "& .MuiDataGrid-columnHeaderFilterIconButton": {
        order: 2,
        display: "inline-flex",
        boxSizing: "border-box",
        width: 28,
        minWidth: 28,
        flexShrink: 0,
        justifyContent: "center",
      },
      // The title element (default or custom renderHeader): fills remaining space
      "& .MuiDataGrid-columnHeaderTitle": {
        order: 0,
        flex: "1 1 auto",
        minWidth: 0,
        overflow: "hidden",
        textOverflow: "ellipsis",
      },
      // Menu icon (three dots on hover): sibling of titleContainer
      "& .MuiDataGrid-menuIcon": {
        width: 28,
        minWidth: 28,
        flexShrink: 0,
        justifyContent: "center",
      },
    },
  };
  if (ep.sx) {
    ep.sx = { ...headerIconSx, ...ep.sx };
  } else {
    ep.sx = headerIconSx;
  }

  const shouldAlwaysShowFilterIcon =
    alwaysShowFilterIcon !== undefined
      ? !!alwaysShowFilterIcon
      : (always_show_filter_icon !== undefined ? !!always_show_filter_icon : false);
  if (shouldAlwaysShowFilterIcon) {
    const existingSlots = ep.slots || {};
    if (!existingSlots.columnHeaderFilterIconButton) {
      ep.slots = {
        ...existingSlots,
        columnHeaderFilterIconButton: _AlwaysVisibleFilterIconButton,
      };
    }
  }

  // When server-side filtering is active, use the custom filter panel
  // with Apply/Reset buttons so every keystroke doesn't trigger a query.
  if (ep.filterMode === "server") {
    const existingSlots = ep.slots || {};
    if (!existingSlots.filterPanel) {
      ep.slots = {
        ...existingSlots,
        filterPanel: _FilterPanelWithApply,
      };
    }
  }

  if (pagination === false) {
    if (unlimitedMode) {
      // Patch active: put all rows on one "page" for continuous scrolling.
      const totalRows = rest.rows ? rest.rows.length : (rest.rowCount || 0);
      if (totalRows > 0) {
        ep.paginationModel = { page: 0, pageSize: totalRows };
        ep.pageSizeOptions = [totalRows];
      }
      if (ep.hideFooter === undefined) ep.hideFooter = true;
    } else {
      // Fallback: use autoPageSize (respects the 100-row cap).
      ep.autoPageSize = true;
      if (ep.hideFooter === undefined) ep.hideFooter = false;
    }
  } else if (pagination !== undefined) {
    ep.pagination = pagination;
  }

  return ep;
}

// ---------------------------------------------------------------------------
// 7. UnlimitedDataGrid wrapper component
// ---------------------------------------------------------------------------
const UnlimitedDataGrid = React.forwardRef((props, ref) => {
  const { onRowsScrollEnd, scrollEndThreshold, debugLog } = props;
  const log = !!debugLog;
  const containerRef = React.useRef(null);
  const scrollEndLockedRef = React.useRef(false);
  const renderCountRef = React.useRef(0);
  const rowsLength = Array.isArray(props.rows) ? props.rows.length : 0;

  renderCountRef.current++;
  _dgLog(log, "render", {
    renderCount: renderCountRef.current,
    rows: rowsLength,
    pagination: props.pagination,
    patchActive: _muiPatchActive,
  });

  // Unlock when new rows arrive so another near-end trigger can fire.
  React.useEffect(() => {
    scrollEndLockedRef.current = false;
    _dgLog(log, "rows updated", { count: rowsLength });
  }, [rowsLength, log]);

  // Attach scroll listener to MUI virtual scroller.
  // IMPORTANT: rowsLength is intentionally excluded from the dependency
  // array.  The listener does not need re-attaching when rows change —
  // the unlock effect above releases the lock, and the next user-driven
  // scroll event will trigger loading.  Including rowsLength caused an
  // infinite loop: each row append re-ran this effect, which called
  // onScroll() immediately before MUI updated the virtual scroller's
  // dimensions, making `remaining` appear small and firing scroll-end
  // again (row append → effect re-run → onScroll → fire → row append …).
  React.useEffect(() => {
    if (typeof onRowsScrollEnd !== "function") return;
    const container = containerRef.current;
    if (!container) return;

    const scroller = container.querySelector(".MuiDataGrid-virtualScroller");
    if (!scroller) {
      _dgLog(log, "WARN: .MuiDataGrid-virtualScroller not found");
      return;
    }
    _dgLog(log, "scroll listener attached", {
      scrollHeight: scroller.scrollHeight,
      clientHeight: scroller.clientHeight,
    });

    const threshold =
      typeof scrollEndThreshold === "number" ? scrollEndThreshold : 160;

    const onScroll = () => {
      const remaining =
        scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;

      if (remaining <= threshold) {
        if (!scrollEndLockedRef.current) {
          scrollEndLockedRef.current = true;
          const payload = {
            scrollTop: scroller.scrollTop,
            scrollHeight: scroller.scrollHeight,
            clientHeight: scroller.clientHeight,
            remaining: remaining,
          };
          _dgLog(log, "scroll-end fired", payload);
          onRowsScrollEnd(payload);
        }
      } else if (remaining > threshold * 2) {
        scrollEndLockedRef.current = false;
      }
    };

    scroller.addEventListener("scroll", onScroll, { passive: true });
    // Defer the initial position check to after the browser has painted,
    // ensuring MUI's virtual scroller dimensions are up to date.
    const rafId = requestAnimationFrame(() => onScroll());
    return () => {
      cancelAnimationFrame(rafId);
      scroller.removeEventListener("scroll", onScroll);
    };
  }, [onRowsScrollEnd, scrollEndThreshold, log]);

  // When filterMode="server" and the custom filter panel is active,
  // listen for the _applyFilter custom event dispatched by the Apply
  // button instead of letting MUI fire onFilterModelChange on every
  // keystroke.
  const realOnFilterModelChange = props.onFilterModelChange;
  const isServerFilter = props.filterMode === "server";

  React.useEffect(() => {
    if (!isServerFilter || typeof realOnFilterModelChange !== "function") return;
    const container = containerRef.current;
    if (!container) return;

    const handler = (e) => {
      _dgLog(log, "apply-filter event", e.detail);
      realOnFilterModelChange(e.detail);
    };
    container.addEventListener("_applyFilter", handler);
    return () => container.removeEventListener("_applyFilter", handler);
  }, [isServerFilter, realOnFilterModelChange, log]);

  // Listen for _requestValueOptions events from the filter icon button.
  // Forwards the column field name to the Python handler so value options
  // can be computed on demand (for large datasets where eager init is skipped).
  const onRequestValueOptions = props.onRequestValueOptions;
  React.useEffect(() => {
    if (typeof onRequestValueOptions !== "function") return;
    const container = containerRef.current;
    if (!container) return;

    const handler = (e) => {
      _dgLog(log, "request-value-options", e.detail);
      onRequestValueOptions(e.detail);
    };
    container.addEventListener("_requestValueOptions", handler);
    return () => container.removeEventListener("_requestValueOptions", handler);
  }, [onRequestValueOptions, log]);

  const effectiveProps = _buildGridProps(props, _muiPatchActive);

  // In server filter mode:
  // 1. Remove onFilterModelChange so MUI doesn't call it on every keystroke.
  //    The Apply button dispatches a custom event that we handle above.
  // 2. Replace the controlled filterModel with a local state that only
  //    syncs from the Python prop when it genuinely changes (e.g. after
  //    Apply, Clear All, or preset upload).  This prevents MUI from
  //    resetting the user's in-progress edits on unrelated re-renders.
  const pythonFilterModel = isServerFilter ? props.filterModel : undefined;
  const [localFilterModel, setLocalFilterModel] = React.useState(
    pythonFilterModel || { items: [] }
  );

  // Track the previous Python filter model to detect genuine changes.
  const prevPythonFilterRef = React.useRef(JSON.stringify(pythonFilterModel));
  React.useEffect(() => {
    if (!isServerFilter) return;
    const serialized = JSON.stringify(pythonFilterModel);
    if (serialized !== prevPythonFilterRef.current) {
      prevPythonFilterRef.current = serialized;
      setLocalFilterModel(pythonFilterModel || { items: [] });
    }
  }, [isServerFilter, pythonFilterModel]);

  if (isServerFilter) {
    delete effectiveProps.onFilterModelChange;
    // Use the local filter model instead of the Python-controlled one.
    effectiveProps.filterModel = localFilterModel;

    // Build a set of singleSelect field names for quick lookup.
    const singleSelectFields = new Set(
      (effectiveProps.columns || [])
        .filter((c) => c.type === "singleSelect")
        .map((c) => c.field)
    );

    // Let MUI update the local state when the user edits in the panel.
    // For singleSelect columns, default the operator to "is" when MUI
    // creates a new filter item with an empty/missing operator.
    effectiveProps.onFilterModelChange = (model) => {
      if (singleSelectFields.size > 0 && model && Array.isArray(model.items)) {
        const patched = model.items.map((item) => {
          if (singleSelectFields.has(item.field) && !item.operator) {
            return { ...item, operator: "is" };
          }
          return item;
        });
        setLocalFilterModel({ ...model, items: patched });
      } else {
        setLocalFilterModel(model);
      }
    };
  }

  const grid = React.createElement(MuiDataGrid_, { ...effectiveProps, ref });

  // When we set a large pageSize (unlimited mode), wrap with the Error
  // Boundary so a failed patch doesn't crash the page.
  if (props.pagination === false && _muiPatchActive) {
    const fallback = () => {
      _dgLog(log, "WARN: falling back to paginated mode (patch failed)");
      const safeProps = _buildGridProps(props, false);
      return React.createElement(MuiDataGrid_, { ...safeProps, ref });
    };
    return React.createElement(
      "div",
      { ref: containerRef, style: { width: "100%", height: "100%" } },
      React.createElement(_DataGridGuard, { fallback: fallback }, grid)
    );
  }

  return React.createElement(
    "div",
    { ref: containerRef, style: { width: "100%", height: "100%" } },
    grid
  );
});
UnlimitedDataGrid.displayName = "UnlimitedDataGrid";
"""


# ---------------------------------------------------------------------------
# DataGrid component
# ---------------------------------------------------------------------------

class DataGrid(rx.Component):
    """Reflex wrapper for the MUI X DataGrid (Community, v8).

    The 100-row page-size limit of the Community edition is removed via
    a small JS wrapper (see module docstring).  You can now set any
    ``pageSize`` or pass ``pagination=False`` to disable pagination
    entirely and let the user scroll through all rows.

    Requires a parent container with explicit dimensions.
    Use ``WrappedDataGrid`` (or the ``data_grid`` namespace callable) for
    a version that automatically wraps itself in a sized ``<div>``.
    """

    library: str = "@mui/x-data-grid"
    tag: str = "UnlimitedDataGrid"
    is_default: bool = False

    lib_dependencies: list[str] = [
        "@mui/material@^7.0.0",
        "@emotion/react@^11.14.0",
        "@emotion/styled@^11.14.0",
    ]

    @property
    def import_var(self) -> rx.ImportVar:
        """Override: install the npm package but do NOT emit an import for the tag.

        ``UnlimitedDataGrid`` does not exist in ``@mui/x-data-grid`` -- it is
        defined by ``add_custom_code()``.  Returning ``render=False`` tells
        Reflex to install the package without generating a broken import.
        """
        return rx.ImportVar(tag=None, render=False)

    def add_imports(self) -> dict:
        """Import DataGrid, GridSignature (for ESM patching), and React.

        ``GridSignature`` is imported from the *same* ``@mui/x-data-grid``
        entry point as ``DataGrid``.  This is critical: Vite pre-bundles
        each npm entry point into a single file, so importing from the
        same specifier guarantees both symbols share the same object
        reference.  Mutating ``GridSignature.DataGrid`` in
        ``add_custom_code()`` then propagates to *all* internal MUI
        signature checks within the bundle.
        """
        return {
            "@mui/x-data-grid": [
                rx.ImportVar(tag="DataGrid", alias="MuiDataGrid_"),
                rx.ImportVar(tag="GridSignature", alias="GridSignature_"),
                rx.ImportVar(tag="useGridApiContext", alias="useGridApiContext_"),
                rx.ImportVar(tag="useGridRootProps", alias="useGridRootProps_"),
                rx.ImportVar(tag="GridFilterPanel", alias="GridFilterPanel_"),
            ],
            "react": [rx.ImportVar(tag="React", is_default=True)],
        }

    def add_custom_code(self) -> list[str]:
        """Inject the UnlimitedDataGrid wrapper component into the compiled page."""
        return [_INLINE_WRAPPER_JS]

    # ---- data ----
    rows: rx.Var[list[dict[str, Any]]]
    columns: rx.Var[list[dict[str, Any]]]

    # ---- display ----
    loading: rx.Var[bool]
    density: rx.Var[Literal["comfortable", "compact", "standard"]]
    row_height: rx.Var[int]
    column_header_height: rx.Var[int]
    show_toolbar: rx.Var[bool]
    show_description_in_header: rx.Var[bool]
    autosize_on_mount: rx.Var[bool]
    autosize_options: rx.Var[dict[str, Any]]

    # ---- debug ----
    debug_log: rx.Var[bool]

    # ---- selection ----
    checkbox_selection: rx.Var[bool]
    row_selection: rx.Var[bool]
    disable_row_selection_on_click: rx.Var[bool]

    # ---- pagination ----
    pagination: rx.Var[bool]
    pagination_model: rx.Var[dict[str, int]]
    page_size_options: rx.Var[list[int]]
    auto_page_size: rx.Var[bool]
    scroll_end_threshold: rx.Var[int]
    hide_footer_pagination: rx.Var[bool]
    hide_footer: rx.Var[bool]

    # ---- server-side mode ----
    row_count: rx.Var[int]
    pagination_mode: rx.Var[Literal["client", "server"]]
    filter_mode: rx.Var[Literal["client", "server"]]
    sorting_mode: rx.Var[Literal["client", "server"]]

    # ---- sorting ----
    sort_model: rx.Var[list[dict[str, Any]]]
    sorting_order: rx.Var[list[str | None]]
    disable_column_sorting: rx.Var[bool]

    # ---- filtering ----
    disable_column_filter: rx.Var[bool]
    always_show_filter_icon: rx.Var[bool]
    filter_debounce_ms: rx.Var[int]
    filter_model: rx.Var[dict[str, Any]]
    active_filter_fields: rx.Var[list[str]]

    # ---- column features ----
    column_visibility_model: rx.Var[dict[str, bool]]
    column_grouping_model: rx.Var[list[dict[str, Any]]]
    disable_column_selector: rx.Var[bool]
    disable_density_selector: rx.Var[bool]

    # ---- slots / customisation ----
    slot_props: rx.Var[dict[str, Any]]

    # ---- row identification ----
    get_row_id: rx.Var[Any]

    # ---- event handlers ----
    on_row_click: rx.EventHandler[_on_row_click_spec]
    on_cell_click: rx.EventHandler[_on_cell_click_spec]
    on_sort_model_change: rx.EventHandler[_on_sort_model_change_spec]
    on_filter_model_change: rx.EventHandler[_on_filter_model_change_spec]
    on_pagination_model_change: rx.EventHandler[_on_pagination_model_change_spec]
    on_row_selection_model_change: rx.EventHandler[_on_row_selection_model_change_spec]
    on_column_visibility_model_change: rx.EventHandler[_on_column_visibility_model_change_spec]
    on_rows_scroll_end: rx.EventHandler[_on_rows_scroll_end_spec]
    on_request_value_options: rx.EventHandler[_on_request_value_options_spec]

    @classmethod
    def create(
        cls,
        *children: rx.Component,
        row_id_field: str | None = None,
        **props: Any,
    ) -> rx.Component:
        """Create a DataGrid component.

        Args:
            *children: Child components (typically unused).
            row_id_field: Convenience shortcut – if provided, a JS ``getRowId``
                callback is generated that reads the given field from each row
                object.  Equivalent to ``getRowId={(row) => row.<field>}``.
            **props: All other DataGrid props.

        Returns:
            The DataGrid component.
        """
        if row_id_field is not None:
            props["get_row_id"] = rx.Var(
                f"(row) => row.{row_id_field}"
            )
        return super().create(*children, **props)


# ---------------------------------------------------------------------------
# WrappedDataGrid – auto-sized container
# ---------------------------------------------------------------------------

class WrappedDataGrid(DataGrid):
    """DataGrid wrapped in a ``<div>`` with explicit width / height.

    MUI DataGrid requires a parent container with explicit dimensions.
    This variant pops ``width`` and ``height`` from the props and applies
    them to an outer ``<div>``.

    Dynamic pagination (``auto_page_size=True``) is **on** by default –
    the grid auto-computes how many rows fit in the container and
    paginates accordingly.  Pass ``pagination=False`` to disable
    pagination entirely and scroll through all rows instead (the
    Community edition's 100-row limit is bypassed via the
    ``GridSignature`` patch).
    """

    @classmethod
    def create(cls, *children: rx.Component, **props: Any) -> rx.Component:
        width = props.pop("width", "100%")
        height = props.pop("height", "400px")
        # ``virtual_scroll`` is kept as an alias for backwards compat.
        props.pop("virtual_scroll", None)

        # Default: dynamic pagination with auto page size.
        props.setdefault("pagination", True)
        props.setdefault("auto_page_size", True)
        props.setdefault("hide_footer", False)
        props.setdefault("always_show_filter_icon", True)
        props.setdefault("autosize_on_mount", True)
        props.setdefault("autosize_options", {
            "includeHeaders": True,
            "includeOutliers": True,
            "expand": True,
        })

        # Position the filter/preferences panel below the headers so it
        # does not obscure column titles.
        # Show Filter before Sort in the column menu (3-dots on header hover).
        default_slots = {
            "panel": {"placement": "bottom-end"},
            "columnMenu": {
                "columnMenuFilterItem": {"displayOrder": 0},
                "columnMenuSortItem": {"displayOrder": 100},
            },
        }
        if "slot_props" not in props:
            props["slot_props"] = default_slots
        else:
            existing = props["slot_props"]
            if "columnMenu" not in existing:
                props["slot_props"] = {**existing, "columnMenu": default_slots["columnMenu"]}

        return Div.create(
            super().create(*children, **props),
            width=width,
            height=height,
        )


# ---------------------------------------------------------------------------
# Namespace (so users can write ``data_grid(...)`` and ``data_grid.column_def``)
# ---------------------------------------------------------------------------

class DataGridNamespace(rx.ComponentNamespace):
    """Namespace for the MUI DataGrid component family."""

    column_def = ColumnDef
    root = DataGrid.create
    __call__ = WrappedDataGrid.create


data_grid = DataGridNamespace()
