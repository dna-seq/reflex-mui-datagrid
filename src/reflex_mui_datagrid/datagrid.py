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

const _muiDefaultTheme = createTheme_();

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

  // Apply: send the current grid filter model to the server and close the panel.
  const handleApply = React.useCallback(() => {
    const currentModel = apiRef.current.state.filter.filterModel;
    const event = new CustomEvent("_applyFilter", { detail: currentModel, bubbles: true });
    const el = apiRef.current.rootElementRef?.current;
    if (el) el.dispatchEvent(event);
    apiRef.current.hideFilterPanel();
  }, [apiRef]);

  // Reset: clear all filters, notify the server, and close the panel.
  const handleReset = React.useCallback(() => {
    const emptyModel = { items: [] };
    apiRef.current.setFilterModel(emptyModel);
    const event = new CustomEvent("_applyFilter", { detail: emptyModel, bubbles: true });
    const el = apiRef.current.rootElementRef?.current;
    if (el) el.dispatchEvent(event);
    apiRef.current.hideFilterPanel();
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
function _isColumnFilterable(apiRef, field, rootProps) {
  if (!field || rootProps.disableColumnFilter || rootProps.disable_column_filter) {
    return false;
  }
  const col = apiRef.current.getColumn(field);
  return col && col.filterable !== false;
}

const _AlwaysVisibleFilterIconButton = (props) => {
  const { field, onClick } = props;
  const apiRef = useGridApiContext_();
  const rootProps = useGridRootProps_();

  if (!_isColumnFilterable(apiRef, field, rootProps)) {
    return null;
  }

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
    detail_columns,
    detailColumns,
    detail_height,
    detailHeight,
    detail_labels,
    detailLabels,
    detail_badge_fields,
    detailBadgeFields,
    detail_badge_colors,
    detailBadgeColors,
    detail_renderers,
    detailRenderers,
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

  const renderedColumns = widenedColumns.map((col) => {
    if (col.renderCell || !col.cellRendererType) return col;
    const cfg = col.cellRendererConfig || {};
    const { cellRendererType, cellRendererConfig, ...colRest } = col;
    if (cellRendererType === "badge") {
      colRest.renderCell = (params) => {
        const val = params.value;
        const formattedVal = params.formattedValue || val;
        if (val == null) return "";
        let c = cfg.color || "";
        let bg = cfg.bgColor || "";
        const colorMap = cfg.colorMap || {};
        const bgColorMap = cfg.bgColorMap || {};
        if (colorMap.hasOwnProperty(val)) c = colorMap[val];
        if (bgColorMap.hasOwnProperty(val)) bg = bgColorMap[val];
        return React.createElement("div", {
          style: {
            color: c || "inherit",
            backgroundColor: bg || "transparent",
            borderRadius: cfg.borderRadius || "16px",
            padding: cfg.padding || "4px 8px",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontWeight: "500",
            fontSize: "0.85em",
            lineHeight: "1.2",
            minWidth: "24px",
            textAlign: "center",
          },
        }, formattedVal);
      };
    } else if (cellRendererType === "progress_bar") {
      colRest.renderCell = (params) => {
        const val = Number(params.value);
        if (isNaN(val)) return "";
        const min = cfg.minValue ?? 0;
        const max = cfg.maxValue ?? 100;
        const percent = Math.max(0, Math.min(100, ((val - min) / (max - min)) * 100));
        const formattedVal = params.formattedValue || params.value;
        const barColor = cfg.color || "#1976d2";
        const trackColor = cfg.trackColor || "#e0e0e0";
        const barHeight = cfg.height || "8px";
        const bar = React.createElement("div", {
          style: { flex: 1, height: barHeight, backgroundColor: trackColor, borderRadius: "4px", overflow: "hidden" },
        }, React.createElement("div", {
          style: { width: `${percent}%`, height: "100%", backgroundColor: barColor, borderRadius: "4px" },
        }));
        if (cfg.showValue === false) {
          return React.createElement("div", { style: { width: "100%", height: "100%", display: "flex", alignItems: "center" } }, bar);
        }
        return React.createElement("div", {
          style: { width: "100%", height: "100%", display: "flex", alignItems: "center", gap: "8px" },
        }, bar, React.createElement("span", {
          style: { fontSize: "0.85em", minWidth: "40px", textAlign: "right" },
        }, formattedVal));
      };
    } else if (cellRendererType === "url") {
      colRest.renderCell = (params) => {
        const val = params.value;
        if (val == null) return "";
        const baseUrl = cfg.baseUrl || "";
        const suffixUrl = cfg.suffixUrl || "";
        const href = baseUrl ? (baseUrl + val + suffixUrl) : (val + suffixUrl);
        const label = cfg.labelField ? params.row[cfg.labelField] : val;
        return React.createElement("a", {
          href, target: cfg.target || "_blank", rel: "noopener noreferrer",
          style: { color: cfg.color || "inherit" },
        }, label);
      };
    }
    return colRest;
  });

  const enhancedColumns = _enhanceColumnsWithDescriptions(
    renderedColumns, showDescriptionInHeader
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
  const detailPanelSx = {
    '& .MuiDataGrid-cell[data-field="__detail_expand__"]': {
      padding: 0,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      cursor: "pointer",
      borderRight: "none",
    },
    '& .MuiDataGrid-columnHeader[data-field="__detail_expand__"]': {
      padding: 0,
      minWidth: "40px !important",
    },
  };
  if (ep.sx) {
    ep.sx = { ...headerIconSx, ...detailPanelSx, ...ep.sx };
  } else {
    ep.sx = { ...headerIconSx, ...detailPanelSx };
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

    // MUI's default toolbar quick filter is client-oriented. In server mode
    // our Python backend only applies explicit column filters via Apply, so
    // hide quick search by default to avoid showing a non-functional control.
    const existingSlotProps = ep.slotProps || {};
    const existingToolbarSlotProps = existingSlotProps.toolbar || {};
    ep.slotProps = {
      ...existingSlotProps,
      toolbar: {
        ...existingToolbarSlotProps,
        showQuickFilter:
          existingToolbarSlotProps.showQuickFilter !== undefined
            ? existingToolbarSlotProps.showQuickFilter
            : false,
      },
    };
  }

  // MUI DataGrid v8 expects rowSelectionModel ids as a Set, but JSON only supports Arrays.
  if (ep.rowSelectionModel && Array.isArray(ep.rowSelectionModel.ids)) {
    ep.rowSelectionModel = {
      type: ep.rowSelectionModel.type || "include",
      ids: new Set(ep.rowSelectionModel.ids),
    };
  }

  if (pagination === false) {
    if (unlimitedMode) {
      // Patch active: put all rows on one "page" for continuous scrolling.
      // Use ep.rows (which may include injected detail rows) if available.
      const totalRows = ep.rows ? ep.rows.length : (rest.rows ? rest.rows.length : (rest.rowCount || 0));
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
// ---------------------------------------------------------------------------
// 7a. Detail panel helpers — React element builders for the setPanels API.
//     These return React elements (not HTML strings) so the virtualiser can
//     render them natively alongside rows.
// ---------------------------------------------------------------------------

// Tone-to-color mapping for rich detail renderers.
const _TONE_COLORS = {
  neutral:  { fg: "#616161", bg: "#f5f5f5", border: "#bdbdbd" },
  good:     { fg: "#2e7d32", bg: "#e8f5e9", border: "#81c784" },
  info:     { fg: "#1565c0", bg: "#e3f2fd", border: "#64b5f6" },
  warning:  { fg: "#e65100", bg: "#fff3e0", border: "#ffb74d" },
  danger:   { fg: "#c62828", bg: "#ffebee", border: "#ef9a9a" },
};
function _toneStyle(tone) {
  return _TONE_COLORS[tone] || _TONE_COLORS.neutral;
}

// ---- Rich detail renderer: badge_list ----
function _renderBadgeList(data) {
  if (!Array.isArray(data)) return null;
  const badges = data.map(function(item, i) {
    var tc = _toneStyle(item.tone);
    return React.createElement("span", {
      key: i,
      style: {
        display: "inline-block", padding: "4px 12px", borderRadius: 4,
        fontSize: 12, fontWeight: 500, letterSpacing: "0.02em",
        background: tc.bg, color: tc.fg, border: "1px solid " + tc.border,
        whiteSpace: "nowrap",
      },
    }, item.label || "");
  });
  return React.createElement("div", {
    style: { display: "flex", flexWrap: "wrap", gap: 6, padding: "4px 0" },
  }, ...badges);
}

// ---- Rich detail renderer: link_list ----
function _renderLinkList(data, config) {
  if (!Array.isArray(data)) return null;
  const links = [];
  const baseUrl = (config && config.baseUrl) || "";
  const suffixUrl = (config && config.suffixUrl) || "";
  const target = (config && config.target) || "_blank";
  data.forEach(function(item, i) {
    if (!item) return;
    const label = item.label != null ? String(item.label) : String(item.value || "");
    if (!label) return;
    const href = item.url || (baseUrl ? (baseUrl + label + suffixUrl) : "");
    if (i > 0) {
      links.push(React.createElement("span", {
        key: "sep_" + i,
        style: { color: "rgba(0,0,0,0.45)" },
      }, ", "));
    }
    if (href) {
      links.push(React.createElement("a", {
        key: "link_" + i,
        href: href,
        target: target,
        rel: "noopener noreferrer",
        style: {
          color: item.color || "#1565c0",
          textDecoration: "none",
          fontWeight: 600,
        },
      }, label));
    } else {
      links.push(React.createElement("span", {
        key: "label_" + i,
        style: { fontWeight: 600 },
      }, label));
    }
  });
  return React.createElement("div", {
    style: {
      display: "flex", flexWrap: "wrap", alignItems: "center",
      gap: 0, padding: "4px 0", fontSize: 13, lineHeight: 1.6,
    },
  }, ...links);
}

// ---- Rich detail renderer: key_value_list ----
function _renderKeyValueList(data) {
  if (!Array.isArray(data)) return null;
  var rows = data.map(function(item, i) {
    var tc = _toneStyle(item.tone);
    return React.createElement("div", {
      key: i,
      style: {
        display: "flex", alignItems: "baseline", gap: 12,
        padding: "6px 0", borderBottom: "1px solid rgba(0,0,0,0.06)",
      },
    },
      React.createElement("span", {
        style: { fontWeight: 600, minWidth: 160, flexShrink: 0, color: "rgba(0,0,0,0.6)", fontSize: 13 },
      }, (item.label || "") + ":"),
      React.createElement("span", {
        style: { color: tc.fg, fontWeight: item.tone ? 600 : 400, fontSize: 13 },
      }, item.value != null ? String(item.value) : ""),
      item.subtext ? React.createElement("span", {
        style: { color: "rgba(0,0,0,0.45)", fontSize: 11, marginLeft: 6 },
      }, item.subtext) : null
    );
  });
  return React.createElement("div", { style: { padding: "2px 0" } }, ...rows);
}

// ---- Rich detail renderer: metric_list ----
function _renderMetricList(data) {
  if (!Array.isArray(data)) return null;
  var cards = data.map(function(item, i) {
    var tc = _toneStyle(item.tone);
    return React.createElement("div", {
      key: i,
      style: {
        display: "flex", flexDirection: "column", padding: "10px 16px",
        borderRadius: 6, background: tc.bg, border: "1px solid " + tc.border,
        minWidth: 140, flex: "1 1 140px", maxWidth: 260,
      },
    },
      React.createElement("div", {
        style: { fontSize: 11, color: "rgba(0,0,0,0.55)", marginBottom: 2, fontWeight: 500 },
      }, item.label || ""),
      React.createElement("div", {
        style: { fontSize: 18, fontWeight: 700, color: tc.fg, lineHeight: 1.3 },
      }, item.value != null ? String(item.value) : ""),
      item.subtext ? React.createElement("div", {
        style: { fontSize: 11, color: "rgba(0,0,0,0.45)", marginTop: 3, lineHeight: 1.3 },
      }, item.subtext) : null
    );
  });
  return React.createElement("div", {
    style: { display: "flex", flexWrap: "wrap", gap: 10, padding: "4px 0" },
  }, ...cards);
}

function _formatDetailValue(value) {
  if (value == null || value === "") return "N/A";
  return String(value);
}

function _buildPercentileSidePanel(data, config, items, outlierSet) {
  if (config && config.showSidePanel === false) return null;

  var sideItems = Array.isArray(data.sideItems) ? data.sideItems : null;
  if (!sideItems) {
    var score = data.score != null ? data.score : data.median;
    sideItems = [
      {
        label: "Your percentile",
        value: score != null ? Math.round(Number(score)) + "th" : "Not available",
        tone: score == null ? "neutral" : (Number(score) < 25 ? "good" : (Number(score) < 75 ? "warning" : "danger")),
      },
      { label: "Reference populations", value: String(items.length), tone: "info" },
      {
        label: "Outliers",
        value: String(outlierSet.size),
        tone: outlierSet.size > 0 ? "warning" : "good",
      },
    ];
  }

  var cards = sideItems.map(function(item, i) {
    var tc = _toneStyle(item.tone);
    return React.createElement("div", {
      key: "side_" + i,
      style: {
        padding: "8px 10px",
        borderRadius: 6,
        background: tc.bg,
        border: "1px solid " + tc.border,
      },
    },
      React.createElement("div", {
        style: { fontSize: 10, color: "rgba(0,0,0,0.55)", fontWeight: 600, marginBottom: 2 },
      }, item.label || ""),
      React.createElement("div", {
        style: { fontSize: 14, color: tc.fg, fontWeight: 700, lineHeight: 1.25 },
      }, _formatDetailValue(item.value)),
      item.subtext ? React.createElement("div", {
        style: { fontSize: 10, color: "rgba(0,0,0,0.52)", marginTop: 3, lineHeight: 1.25 },
      }, item.subtext) : null
    );
  });

  var summaryPlacement = (config && config.summaryPlacement) || "sidePanel";
  var summary = data.summary && summaryPlacement === "sidePanel" ? React.createElement("div", {
    style: {
      padding: "8px 10px",
      borderRadius: 6,
      background: "#fafafa",
      border: "1px solid rgba(0,0,0,0.10)",
      fontSize: 11,
      color: "rgba(0,0,0,0.62)",
      lineHeight: 1.35,
      fontStyle: "italic",
    },
  }, data.summary) : null;

  var title = (config && config.sidePanelTitle) || "Interpretation";
  return React.createElement("div", {
    style: {
      flex: "0 0 220px",
      maxWidth: 260,
      display: "flex",
      flexDirection: "column",
      gap: 8,
      alignSelf: "stretch",
      paddingTop: 6,
    },
  },
    React.createElement("div", {
      style: { fontSize: 11, fontWeight: 700, color: "rgba(0,0,0,0.62)", letterSpacing: "0.02em" },
    }, title),
    ...cards,
    summary
  );
}

function _buildPercentileSummary(data, config) {
  var summaryPlacement = (config && config.summaryPlacement) || "sidePanel";
  if (!data || !data.summary || summaryPlacement !== "fullWidth") return null;
  return React.createElement("div", {
    style: {
      flex: "1 1 100%",
      width: "100%",
      padding: "8px 10px",
      borderRadius: 6,
      background: "#fafafa",
      border: "1px solid rgba(0,0,0,0.10)",
      fontSize: 11,
      color: "rgba(0,0,0,0.62)",
      lineHeight: 1.35,
      fontStyle: "italic",
      boxSizing: "border-box",
    },
  }, data.summary);
}

// ---- Rich detail renderer: percentile_spread ----
function _renderPercentileSpread(data, config) {
  if (!data || typeof data !== "object") return null;
  config = Object.assign({}, config || {}, data.rendererConfig || data.config || {});
  var scaleMin = (config && config.scaleMin != null) ? config.scaleMin : 0;
  var scaleMax = (config && config.scaleMax != null) ? config.scaleMax : 100;
  var range = scaleMax - scaleMin || 1;
  var items = Array.isArray(data.items) ? data.items : [];
  var outlierSet = new Set(Array.isArray(data.outliers) ? data.outliers : []);

  var bands = (config && Array.isArray(config.bands)) ? config.bands : [
    { from: 25, to: 75, label: "average range" },
  ];

  var bandEls = bands.map(function(band, i) {
    var left = ((band.from - scaleMin) / range) * 100;
    var width = ((band.to - band.from) / range) * 100;
    return React.createElement("div", {
      key: "band_" + i,
      title: band.label || "",
      style: {
        position: "absolute", top: 0, bottom: 0,
        left: left + "%", width: width + "%",
        background: "rgba(25, 118, 210, 0.10)",
        borderLeft: "1px dashed rgba(25, 118, 210, 0.3)",
        borderRight: "1px dashed rgba(25, 118, 210, 0.3)",
      },
    });
  });

  var markerEls = items.map(function(item, i) {
    var val = Number(item.value);
    if (isNaN(val)) return null;
    var pct = ((val - scaleMin) / range) * 100;
    pct = Math.max(0, Math.min(100, pct));
    var isOutlier = outlierSet.has(item.label);
    var tc = _toneStyle(item.tone || (isOutlier ? "danger" : "info"));
    return React.createElement("div", {
      key: "marker_" + i,
      title: (item.label || "") + ": " + val,
      style: {
        position: "absolute", top: -4, width: isOutlier ? 14 : 10, height: isOutlier ? 14 : 10,
        borderRadius: "50%", background: tc.fg, border: "2px solid " + tc.border,
        left: "calc(" + pct + "% - " + (isOutlier ? 7 : 5) + "px)",
        zIndex: isOutlier ? 2 : 1, cursor: "default",
        boxShadow: isOutlier ? "0 0 4px " + tc.fg : "none",
      },
    });
  });

  var medianEl = null;
  var _spreadScore = data.score != null ? data.score : data.median;
  if (_spreadScore != null) {
    var medPct = ((Number(_spreadScore) - scaleMin) / range) * 100;
    medPct = Math.max(0, Math.min(100, medPct));
    medianEl = React.createElement("div", {
      title: "Your score: " + _spreadScore,
      style: {
        position: "absolute", top: -6, left: "calc(" + medPct + "% - 1px)",
        width: 2, height: 20, background: "#f57c00", zIndex: 3,
      },
    });
  }

  var labelEls = items.map(function(item, i) {
    var val = Number(item.value);
    if (isNaN(val)) return null;
    var pct = ((val - scaleMin) / range) * 100;
    pct = Math.max(0, Math.min(100, pct));
    var isOutlier = outlierSet.has(item.label);
    var tc = _toneStyle(item.tone || (isOutlier ? "danger" : "info"));
    return React.createElement("div", {
      key: "lbl_" + i,
      style: {
        position: "absolute", top: 16,
        left: pct + "%", transform: "translateX(-50%)",
        fontSize: 9, color: tc.fg, whiteSpace: "nowrap",
        fontWeight: isOutlier ? 700 : 400,
      },
    }, item.label || "");
  });

  var track = React.createElement("div", {
    style: {
      position: "relative", height: 8, background: "#e0e0e0",
      borderRadius: 4, width: "100%",
    },
  }, ...bandEls, ...markerEls, medianEl);

  var legendRow = React.createElement("div", {
    style: { position: "relative", height: 22, width: "100%" },
  }, ...labelEls);

  var scaleLabels = React.createElement("div", {
    style: { display: "flex", justifyContent: "space-between", fontSize: 10, color: "#999", marginTop: 2 },
  },
    React.createElement("span", null, String(scaleMin)),
    React.createElement("span", null, String(scaleMax))
  );

  var summaryPlacement = (config && config.summaryPlacement) || "sidePanel";
  var summaryEl = data.summary && summaryPlacement === "chart" ? React.createElement("div", {
    style: { fontSize: 11, color: "rgba(0,0,0,0.55)", marginTop: 6, fontStyle: "italic" },
  }, data.summary) : null;

  var chart = React.createElement("div", {
    style: { padding: "8px 0", flex: "1 1 420px", minWidth: 320, maxWidth: 560 },
  }, track, legendRow, scaleLabels, summaryEl);
  var sidePanel = _buildPercentileSidePanel(data, config, items, outlierSet);
  var fullWidthSummary = _buildPercentileSummary(data, config);

  return React.createElement("div", {
    style: {
      padding: "8px 0",
      width: "100%",
      maxWidth: (config && config.maxWidth) || 860,
      display: "flex",
      gap: 18,
      alignItems: "flex-start",
      flexWrap: "wrap",
    },
  }, chart, sidePanel, fullWidthSummary);
}

// ---- Rich detail renderer: bell_curve ----
// Normal PDF and inverse CDF (Beasley-Springer-Moro rational approximation).
function _normalPdf(x) {
  return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
}
function _percentileToZ(p) {
  if (p <= 0) return -3.5;
  if (p >= 1) return 3.5;
  var a = [0, -3.969683028665376e1, 2.209460984245205e2,
    -2.759285104469687e2, 1.383577518672690e2,
    -3.066479806614716e1, 2.506628277459239e0];
  var b = [0, -5.447609879822406e1, 1.615858368580409e2,
    -1.556989798598866e2, 6.680131188771972e1, -1.328068155288572e1];
  var c = [0, -7.784894002430293e-3, -3.223964580411365e-1,
    -2.400758277161838e0, -2.549732539343734e0,
    4.374664141464968e0, 2.938163982698783e0];
  var d = [0, 7.784695709041462e-3, 3.224671290700398e-1,
    2.445134137142996e0, 3.754408661907416e0];
  var pLow = 0.02425, pHigh = 1 - pLow;
  var q, r;
  if (p < pLow) {
    q = Math.sqrt(-2 * Math.log(p));
    return (((((c[1]*q+c[2])*q+c[3])*q+c[4])*q+c[5])*q+c[6]) /
           ((((d[1]*q+d[2])*q+d[3])*q+d[4])*q+1);
  } else if (p <= pHigh) {
    q = p - 0.5; r = q * q;
    return (((((a[1]*r+a[2])*r+a[3])*r+a[4])*r+a[5])*r+a[6])*q /
           (((((b[1]*r+b[2])*r+b[3])*r+b[4])*r+b[5])*r+1);
  } else {
    q = Math.sqrt(-2 * Math.log(1 - p));
    return -(((((c[1]*q+c[2])*q+c[3])*q+c[4])*q+c[5])*q+c[6]) /
            ((((d[1]*q+d[2])*q+d[3])*q+d[4])*q+1);
  }
}

var _plotlyImportPromise = null;
var _PlotComponent = null;
var _plotlyFailed = false;

function _resolvePlotComponent(mod) {
  if (typeof mod === "function") return mod;
  if (mod && typeof mod.default === "function") return mod.default;
  if (mod && mod.default && typeof mod.default.default === "function") return mod.default.default;
  if (mod && typeof mod.Plot === "function") return mod.Plot;
  return null;
}

function _numberConfig(config, key, fallback) {
  var value = Number(config && config[key]);
  return Number.isFinite(value) ? value : fallback;
}

function _bellCurveLabelOffset(zVal, placedLabels, config) {
  // Place each label in the first non-colliding slot of a 3-column grid
  // (center / left / right) repeated upward across rows. Tier order is
  // center-row0, left-row0, right-row0, center-row1, left-row1, right-row1, ...
  // so two close-by labels separate horizontally before stacking vertically.
  var minGap = _numberConfig(config, "labelMinGapZ", 0.24);
  var maxTiers = Math.max(1, Math.floor(_numberConfig(config, "labelTiers", 9)));
  var baseOffset = _numberConfig(config, "labelYOffset", 22);
  var stepOffset = _numberConfig(config, "labelYOffsetStep", 18);
  var xStep = _numberConfig(config, "labelXOffsetStep", 24);
  var tier = 0;

  for (var candidate = 0; candidate < maxTiers; candidate++) {
    var collides = placedLabels.some(function(label) {
      return label.tier === candidate && Math.abs(label.z - zVal) < minGap;
    });
    if (!collides) {
      tier = candidate;
      break;
    }
    tier = candidate;
  }
  placedLabels.push({ z: zVal, tier: tier });

  var colOrder = [0, -1, 1];
  var col = colOrder[tier % 3];
  var row = Math.floor(tier / 3);
  return {
    ax: col * xStep,
    ay: -(baseOffset + row * stepOffset),
  };
}

function _BellCurveRenderer(props) {
  var data = props.data;
  var config = Object.assign({}, props.config || {}, (data && (data.rendererConfig || data.config)) || {});
  var _ref = React.useState(0), tick = _ref[0], setTick = _ref[1];

  React.useEffect(function() {
    if (_PlotComponent || _plotlyFailed) return;
    if (!_plotlyImportPromise) {
      _plotlyImportPromise = import("react-plotly.js").then(function(mod) {
        _PlotComponent = _resolvePlotComponent(mod);
        if (!_PlotComponent) _plotlyFailed = true;
      }).catch(function() {
        _plotlyFailed = true;
      });
    }
    _plotlyImportPromise.then(function() { setTick(function(t) { return t + 1; }); });
  }, []);

  if (_plotlyFailed || !data || typeof data !== "object") {
    return _renderPercentileSpread(data, config);
  }
  if (!_PlotComponent) {
    return React.createElement("div", {
      style: { padding: 8, color: "#999", fontSize: 12 },
    }, "Loading chart...");
  }

  var items = Array.isArray(data.items) ? data.items : [];
  var scaleMin = (config && config.scaleMin != null) ? config.scaleMin : 0;
  var scaleMax = (config && config.scaleMax != null) ? config.scaleMax : 100;
  var outlierSet = new Set(Array.isArray(data.outliers) ? data.outliers : []);

  var xCurve = [], yCurve = [];
  for (var i = 0; i <= 200; i++) {
    var z = -3.5 + (i / 200) * 7;
    xCurve.push(z);
    yCurve.push(_normalPdf(z));
  }

  var traces = [{
    x: xCurve, y: yCurve, type: "scatter", mode: "lines",
    fill: "tozeroy", fillcolor: "rgba(25,118,210,0.08)",
    line: { color: "#1976d2", width: 2 },
    hoverinfo: "skip", showlegend: false,
  }];

  var shapes = [];
  var annotations = [];
  var placedLabels = [];
  var labelMode = (config && config.labelMode) || "auto";
  var labelMaxVisible = _numberConfig(config, "labelMaxVisible", 16);
  var showPointLabels = labelMode !== "none" && (labelMode === "always" || items.length <= labelMaxVisible);
  var scoreVal = data.score != null ? data.score : data.median;
  var zScore = null;
  var scoreY = null;
  if (scoreVal != null) {
    var scoreFrac = (Number(scoreVal) - scaleMin) / ((scaleMax - scaleMin) || 1);
    scoreFrac = Math.max(0.001, Math.min(0.999, scoreFrac));
    zScore = _percentileToZ(scoreFrac);
    scoreY = _normalPdf(zScore);
    if (showPointLabels) {
      var reservedScoreTiers = Math.max(0, Math.floor(_numberConfig(config, "scoreLabelReservedTiers", 3)));
      for (var reservedTier = 0; reservedTier < reservedScoreTiers; reservedTier++) {
        placedLabels.push({ z: zScore, tier: reservedTier });
      }
    }
  }

  var bands = (config && Array.isArray(config.bands)) ? config.bands : [
    { from: 25, to: 75, label: "average range" },
  ];
  for (var bi = 0; bi < bands.length; bi++) {
    var band = bands[bi];
    var zFrom = _percentileToZ(band.from / 100);
    var zTo = _percentileToZ(band.to / 100);
    shapes.push({
      type: "rect", xref: "x", yref: "paper",
      x0: zFrom, x1: zTo, y0: 0, y1: 1,
      fillcolor: "rgba(25,118,210,0.06)", line: { width: 0 },
      layer: "below",
    });
  }

  for (var mi = 0; mi < items.length; mi++) {
    var item = items[mi];
    var val = Number(item.value);
    if (isNaN(val)) continue;
    var pFrac = (val - scaleMin) / ((scaleMax - scaleMin) || 1);
    pFrac = Math.max(0.001, Math.min(0.999, pFrac));
    var zVal = _percentileToZ(pFrac);
    var yVal = _normalPdf(zVal);
    var isOutlier = outlierSet.has(item.label);
    var tc = _toneStyle(item.tone || (isOutlier ? "danger" : "info"));

    shapes.push({
      type: "line", xref: "x", yref: "paper",
      x0: zVal, x1: zVal, y0: 0, y1: 0.95,
      line: { color: tc.fg, width: isOutlier ? 2.5 : 1.5, dash: isOutlier ? "solid" : "dot" },
    });

    traces.push({
      x: [zVal], y: [yVal], type: "scatter", mode: "markers",
      marker: {
        size: Number(item.markerSize) || (isOutlier ? 12 : 9),
        color: item.markerColor || tc.fg,
        line: { color: "#fff", width: 1.5 },
        symbol: item.symbol || (isOutlier ? "diamond" : "circle"),
      },
      name: item.label,
      text: [(item.label || "") + ": " + val + "th pct"],
      hoverinfo: "text",
      showlegend: true,
    });

    if (showPointLabels) {
      var labelOffset = _bellCurveLabelOffset(zVal, placedLabels, config);
      annotations.push({
        x: zVal, y: yVal, xref: "x", yref: "y",
        text: item.label || "", showarrow: true,
        arrowhead: 0, arrowcolor: item.markerColor || tc.fg,
        ax: labelOffset.ax, ay: labelOffset.ay,
        font: { size: _numberConfig(config, "labelFontSize", 10), color: item.markerColor || tc.fg, weight: isOutlier ? 700 : 400 },
      });
    }
  }

  if (scoreVal != null && zScore != null && scoreY != null) {
    shapes.push({
      type: "line", xref: "x", yref: "paper",
      x0: zScore, x1: zScore, y0: 0, y1: 1,
      line: { color: "#f57c00", width: 2 },
    });
    var scoreLabel = data.scoreLabel || "you (" + Math.round(Number(scoreVal)) + "th)";
    var scoreLabelText = "<b>" + scoreLabel + "</b>";
    annotations.push({
      x: zScore, y: scoreY, xref: "x", yref: "y",
      text: scoreLabelText, showarrow: true,
      arrowhead: 0, arrowcolor: "#f57c00",
      ax: _numberConfig(config, "scoreLabelXOffset", 0),
      ay: -_numberConfig(config, "scoreLabelYOffset", 26),
      font: {
        size: _numberConfig(config, "scoreLabelFontSize", 13),
        color: (config && config.scoreLabelColor) || "#e65100",
      },
      bgcolor: (config && config.scoreLabelBgColor) || "rgba(255,255,255,0.92)",
      bordercolor: (config && config.scoreLabelBorderColor) || "rgba(245,124,0,0.55)",
      borderpad: _numberConfig(config, "scoreLabelBorderPad", 3),
    });
  }

  var chartHeight = Number(config && config.height);
  if (!Number.isFinite(chartHeight) || chartHeight <= 0) chartHeight = 300;
  var maxWidth = Number(config && config.maxWidth);
  if (!Number.isFinite(maxWidth) || maxWidth <= 0) maxWidth = 860;
  // Layout defaults intentionally match the historical bell curve so the
  // curve shape and chart aspect stay stable; consumers can override
  // individual values via the renderer config when more headroom is needed.
  var marginTop = _numberConfig(config, "marginTop", 18);
  var marginBottom = _numberConfig(config, "marginBottom", 48);
  var legendY = _numberConfig(config, "legendY", -0.22);
  var yAxisMax = _numberConfig(config, "yAxisMax", 0.45);
  var xTitleStandoffRaw = Number(config && config.xTitleStandoff);
  var xaxisTitle = { text: "Percentile", font: { size: 11 } };
  if (Number.isFinite(xTitleStandoffRaw) && xTitleStandoffRaw > 0) {
    xaxisTitle.standoff = xTitleStandoffRaw;
  }

  var layout = {
    autosize: true, height: chartHeight, margin: { l: 44, r: 28, t: marginTop, b: marginBottom },
    xaxis: {
      title: xaxisTitle,
      tickvals: [-2.326, -1.645, -0.674, 0, 0.674, 1.645, 2.326],
      ticktext: ["1", "5", "25", "50", "75", "95", "99"],
      range: [-3.5, 3.5], zeroline: false,
    },
    yaxis: { visible: false, range: [0, yAxisMax] },
    shapes: shapes, annotations: annotations,
    legend: { orientation: "h", y: legendY, x: 0.5, xanchor: "center", font: { size: 11 } },
    plot_bgcolor: "rgba(0,0,0,0)",
    paper_bgcolor: "rgba(0,0,0,0)",
    hoverlabel: { font: { size: 11 } },
  };

  var summaryPlacement = (config && config.summaryPlacement) || "sidePanel";
  var summaryEl = data.summary && summaryPlacement === "chart" ? React.createElement("div", {
    style: { fontSize: 11, color: "rgba(0,0,0,0.55)", marginTop: 4, fontStyle: "italic" },
  }, data.summary) : null;
  var chart = React.createElement("div", {
    style: { flex: "1 1 520px", minWidth: 380 },
  },
    React.createElement(_PlotComponent, {
      data: traces, layout: layout,
      config: { staticPlot: false, displayModeBar: false, responsive: true },
      useResizeHandler: true,
      style: { width: "100%", height: chartHeight },
    }),
    summaryEl
  );
  var sidePanel = _buildPercentileSidePanel(data, config, items, outlierSet);
  var fullWidthSummary = _buildPercentileSummary(data, config);

  return React.createElement("div", {
    style: {
      padding: "6px 0",
      width: "100%",
      maxWidth: maxWidth,
      margin: "0",
      display: "flex",
      gap: 18,
      alignItems: "flex-start",
      flexWrap: "wrap",
    },
  }, chart, sidePanel, fullWidthSummary);
}

function _smartBadgeColor(text) {
  const t = text.toLowerCase();
  if (/^pgs\\d/i.test(t))                             return ["#37474f","#eceff1"];
  if (/below average|low risk/i.test(t))              return ["#c62828","#ffcdd2"];
  if (/above average|high risk|elevated/i.test(t))    return ["#2e7d32","#c8e6c9"];
  if (/average|moderate/i.test(t))                    return ["#e65100","#fff3e0"];
  if (/quality:\\s*high/i.test(t))                     return ["#2e7d32","#e8f5e9"];
  if (/quality:\\s*moderate/i.test(t))                 return ["#f57f17","#fff8e1"];
  if (/quality:\\s*low/i.test(t))                      return ["#c62828","#ffebee"];
  if (/percentile/i.test(t))                          return ["#1565c0","#e3f2fd"];
  if (/pop:|population/i.test(t))                     return ["#00695c","#e0f2f1"];
  if (/ref:|reference/i.test(t))                      return ["#6a1b9a","#f3e5f5"];
  return ["#455a64","#eceff1"];
}

function _computeDetailPanelHeight(detailHeight, detailCols) {
  const configured = Number(detailHeight);
  if (Number.isFinite(configured) && configured > 0) return configured;
  const count = Array.isArray(detailCols) ? detailCols.length : 0;
  return Math.max(120, count * 32 + 24);
}

function _defaultRowHeightForParams(gridProps, params) {
  const explicit = Number(gridProps && (gridProps.rowHeight || gridProps.row_height));
  const base = Number.isFinite(explicit) && explicit > 0 ? explicit : 52;
  if (params && typeof params.densityFactor === "number") {
    return base * params.densityFactor;
  }
  const density = gridProps && gridProps.density;
  if (density === "compact") return base * 0.7;
  if (density === "comfortable") return base * 1.3;
  return base;
}

function _buildDetailPanelElement(row, detailCols, detailLabels, columns, badgeFields, badgeColors, detailRenderers) {
  const _badgeFieldSet = new Set(badgeFields || []);
  const _badgeColorMap = badgeColors || {};
  const _renderers = detailRenderers || {};
  const items = detailCols.map((field, idx) => {
    const val = row[field];
    let label = (detailLabels || {})[field];
    if (!label) {
      const colDef = (columns || []).find((c) => c.field === field);
      label = (colDef && (colDef.headerName || colDef.header_name)) || field;
    }

    // Check for a rich renderer config for this field.
    var rendererCfg = _renderers[field];
    if (rendererCfg && rendererCfg.type) {
      // Structured data may arrive as a JSON string from Reflex serialisation.
      var parsed = val;
      if (typeof val === "string" && val.length > 0 && (val[0] === "[" || val[0] === "{")) {
        try { parsed = JSON.parse(val); } catch(_e) { parsed = val; }
      }
      var richEl = null;
      var rtype = rendererCfg.type;
      if (rtype === "badge_list" && Array.isArray(parsed)) {
        richEl = _renderBadgeList(parsed);
      } else if (rtype === "link_list" && Array.isArray(parsed)) {
        richEl = _renderLinkList(parsed, rendererCfg);
      } else if (rtype === "key_value_list" && Array.isArray(parsed)) {
        richEl = _renderKeyValueList(parsed);
      } else if (rtype === "metric_list" && Array.isArray(parsed)) {
        richEl = _renderMetricList(parsed);
      } else if (rtype === "percentile_spread" && parsed && typeof parsed === "object") {
        richEl = _renderPercentileSpread(parsed, rendererCfg);
      } else if (rtype === "bell_curve" && parsed && typeof parsed === "object") {
        richEl = React.createElement(_BellCurveRenderer, { data: parsed, config: rendererCfg });
      }
      // If the rich renderer produced output, wrap with label.
      if (richEl) {
        return React.createElement("div", {
          key: field,
          style: { padding: "8px 0", borderBottom: "1px solid rgba(0,0,0,0.06)" },
        },
          React.createElement("div", {
            style: { fontWeight: 600, color: "rgba(0,0,0,0.6)", fontSize: 12, marginBottom: 6 },
          }, label),
          richEl
        );
      }
      // Fallback: degrade to text for malformed data.
    }

    const valStr = val != null ? String(val) : "";

    if (_badgeFieldSet.has(field)) {
      const parts = valStr.split("|").map((s) => s.trim()).filter(Boolean);
      const badges = parts.map((p, i) => {
        const customColor = _badgeColorMap[p] || _badgeColorMap[p.toLowerCase()];
        const [fg, bg] = customColor
          ? [customColor[0] || "#455a64", customColor[1] || "#eceff1"]
          : _smartBadgeColor(p);
        return React.createElement("span", {
          key: i,
          style: {
            display: "inline-block", padding: "3px 10px", borderRadius: 3,
            fontSize: 12, fontWeight: 500, letterSpacing: "0.02em",
            background: bg, color: fg, whiteSpace: "nowrap",
          },
        }, p);
      });
      return React.createElement("div", {
        key: field,
        style: {
          display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6,
          padding: "8px 0 10px 0",
          borderBottom: "1px solid rgba(0,0,0,0.08)",
        },
      }, ...badges);
    }

    return React.createElement("div", {
      key: field,
      style: {
        display: "flex", gap: 12, padding: "7px 0",
        fontSize: 13, lineHeight: 1.55,
      },
    },
      React.createElement("span", {
        style: { fontWeight: 600, minWidth: 150, flexShrink: 0, color: "rgba(0,0,0,0.6)" },
      }, label + ":"),
      React.createElement("span", {
        style: { color: "rgba(0,0,0,0.87)", whiteSpace: "pre-wrap", wordBreak: "break-word" },
      }, valStr)
    );
  });
  return items;
}

// ---------------------------------------------------------------------------
// 7b. _DetailPanelsSlot — replaces the no-op Community detailPanels slot.
//     GridVirtualScroller only passes { virtualScroller } to this slot
//     (slotProps.detailPanels is NOT merged), so we read additional data
//     from _detailPanelDataRef — a module-level ref set by each
//     UnlimitedDataGrid instance before render.  For pages with multiple
//     grids, each instance overwrites the ref during its own render phase,
//     which is safe because React renders synchronously.
// ---------------------------------------------------------------------------
const _detailPanelDataRef = { current: null };

function _DetailPanelsSlot(props) {
  const { virtualScroller } = props;
  const data = _detailPanelDataRef.current;
  const setPanels = virtualScroller && virtualScroller.setPanels;

  const expandedRowIds   = data && data.expandedRowIds;
  const detailCols       = data && data.detailCols;
  const detailLabels     = data && data.detailLabels;
  const detailHeight     = data && data.detailHeight;
  const badgeFields      = data && data.badgeFields;
  const badgeColors      = data && data.badgeColors;
  const detailRenderers  = data && data.detailRenderers;
  const rows             = data && data.rows;
  const columns          = data && data.columns;
  const getRowIdFn       = data && data.getRowIdFn;

  React.useEffect(() => {
    if (typeof setPanels !== "function") return;
    if (!expandedRowIds || expandedRowIds.size === 0) {
      setPanels(new Map());
      return;
    }

    const rowById = {};
    for (const row of (rows || [])) {
      const id = getRowIdFn ? getRowIdFn(row) : row.id;
      rowById[id] = row;
    }

    const calcHeight = _computeDetailPanelHeight(detailHeight, detailCols);

    const map = new Map();
    for (const rowId of expandedRowIds) {
      const row = rowById[rowId];
      if (!row) continue;

      const content = _buildDetailPanelElement(row, detailCols, detailLabels, columns, badgeFields, badgeColors, detailRenderers);
      const panel = React.createElement("div", {
        key: "__detail_panel_" + String(rowId),
        style: {
          width: "100%",
          height: calcHeight,
          overflow: "auto",
          padding: "14px 24px 14px 88px",
          boxSizing: "border-box",
          background: "var(--DataGrid-containerBackground, #fafafa)",
          borderBottom: "1px solid var(--DataGrid-rowBorderColor, rgba(224,224,224,1))",
          fontFamily: "var(--DataGrid-fontFamily, inherit)",
          fontSize: "var(--DataGrid-fontSize, 0.875rem)",
        },
      }, ...content);
      map.set(rowId, panel);
    }
    setPanels(map);

    return () => { setPanels(new Map()); };
  }, [setPanels, expandedRowIds, rows, columns, detailCols, detailLabels,
      detailHeight, badgeFields, badgeColors, detailRenderers, getRowIdFn]);

  return null;
}

// ---------------------------------------------------------------------------
// 7b. UnlimitedDataGrid wrapper component
// ---------------------------------------------------------------------------
const UnlimitedDataGrid = React.forwardRef((props, ref) => {
  const { onRowsScrollEnd, scrollEndThreshold, debugLog } = props;
  const log = !!debugLog;
  const containerRef = React.useRef(null);
  const scrollEndLockedRef = React.useRef(false);
  const renderCountRef = React.useRef(0);
  const rowsLength = Array.isArray(props.rows) ? props.rows.length : 0;

  // Row detail panel: track which rows are expanded.
  const [expandedRowIds, setExpandedRowIds] = React.useState(() => new Set());

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
    const rafId = requestAnimationFrame(() => onScroll());
    return () => {
      cancelAnimationFrame(rafId);
      scroller.removeEventListener("scroll", onScroll);
    };
  }, [onRowsScrollEnd, scrollEndThreshold, log]);

  // _applyFilter listener for server-side filtering.
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

  // _requestValueOptions listener.
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

  // ---- Build effective props ----
  const effectiveProps = _buildGridProps(props, _muiPatchActive);

  // ---- Detail panel: expander column + onCellClick toggle ----
  const _detailCols = props.detailColumns || props.detail_columns;
  const _detailLabels = props.detailLabels || props.detail_labels || {};
  const _detailH = props.detailHeight || props.detail_height || 0;
  const _badgeFields = props.detailBadgeFields || props.detail_badge_fields || [];
  const _badgeColors = props.detailBadgeColors || props.detail_badge_colors || {};
  const _detailRenderers = props.detailRenderers || props.detail_renderers || {};
  const hasDetailPanel = Array.isArray(_detailCols) && _detailCols.length > 0;

  if (hasDetailPanel) {
    const _getRowIdFn = effectiveProps.getRowId || ((r) => r.id);

    // Inject expander column after the checkbox column (if present).
    const _toggleDetailRow = (rowId) => {
      setExpandedRowIds((prev) => {
        const next = new Set(prev);
        if (next.has(rowId)) next.delete(rowId);
        else next.add(rowId);
        return next;
      });
    };

    const expanderCol = {
      field: "__detail_expand__",
      headerName: "",
      width: 40,
      minWidth: 40,
      maxWidth: 40,
      sortable: false,
      filterable: false,
      disableColumnMenu: true,
      disableReorder: true,
      resizable: false,
      renderCell: (params) => {
        const rowId = _getRowIdFn(params.row);
        const isExp = expandedRowIds.has(rowId);
        return React.createElement("div", {
          role: "button",
          tabIndex: 0,
          "aria-label": isExp ? "Collapse row details" : "Expand row details",
          "aria-expanded": isExp,
          onClick: (e) => {
            e.stopPropagation();
            e.defaultMuiPrevented = true;
            _toggleDetailRow(rowId);
          },
          onKeyDown: (e) => {
            if (e.key !== "Enter" && e.key !== " ") return;
            e.preventDefault();
            e.stopPropagation();
            e.defaultMuiPrevented = true;
            _toggleDetailRow(rowId);
          },
          style: {
            display: "flex", alignItems: "center",
            justifyContent: "center", width: "100%", height: "100%",
            cursor: "pointer", userSelect: "none",
            color: isExp ? "var(--mui-palette-primary-main, #1976d2)" : "rgba(0,0,0,0.54)",
            transition: "transform 0.2s cubic-bezier(0.4,0,0.2,1), color 0.2s",
            transform: isExp ? "rotate(180deg)" : "rotate(0deg)",
          },
        }, React.createElement("svg", {
          width: 20, height: 20, viewBox: "0 0 24 24",
          fill: "currentColor", xmlns: "http://www.w3.org/2000/svg",
          style: { pointerEvents: "none" },
        }, React.createElement("path", {
          d: "M16.59 8.59L12 13.17 7.41 8.59 6 10l6 6 6-6z",
        })));
      },
    };
    const cols = effectiveProps.columns || [];
    const checkboxIdx = cols.findIndex((c) => c.field === "__check__" || c.field === "__GRID_CHECKBOX_SELECTION_FIELD__");
    if (checkboxIdx >= 0) {
      cols.splice(checkboxIdx + 1, 0, expanderCol);
    } else {
      cols.unshift(expanderCol);
    }
    effectiveProps.columns = cols;

    // Intercept cell clicks on the expander column.
    const origOnCellClick = effectiveProps.onCellClick;
    const origOnRowClick = effectiveProps.onRowClick;
    let _lastClickWasExpander = false;

    effectiveProps.onCellClick = (params, event) => {
      _lastClickWasExpander = false;
      if (params.field === "__detail_expand__") {
        _lastClickWasExpander = true;
        if (event) event.defaultMuiPrevented = true;
        return;
      }
      if (typeof origOnCellClick === "function") origOnCellClick(params, event);
    };

    effectiveProps.onRowClick = (params, event) => {
      if (_lastClickWasExpander) { _lastClickWasExpander = false; return; }
      if (typeof origOnRowClick === "function") origOnRowClick(params, event);
    };
  }

  // ---- Detail panel: wire _DetailPanelsSlot via setPanels API ----
  // Override the Community no-op detailPanels slot with our component that
  // calls virtualScroller.setPanels(map) — the same mechanism MUI X Pro uses.
  // GridVirtualScroller only passes { virtualScroller } to the slot (ignoring
  // slotProps), so we communicate extra data via a module-level ref.
  if (hasDetailPanel) {
    _detailPanelDataRef.current = {
      expandedRowIds: expandedRowIds,
      detailCols: _detailCols,
      detailLabels: _detailLabels,
      detailHeight: _detailH,
      badgeFields: _badgeFields,
      badgeColors: _badgeColors,
      detailRenderers: _detailRenderers,
      rows: props.rows || [],
      columns: effectiveProps.columns || [],
      getRowIdFn: effectiveProps.getRowId || ((r) => r.id),
    };
    const existingSlots = effectiveProps.slots || {};
    effectiveProps.slots = { ...existingSlots, detailPanels: _DetailPanelsSlot };
  }

  // ---- Server filter mode: local filter model ----
  const pythonFilterModel = isServerFilter ? props.filterModel : undefined;
  const [localFilterModel, setLocalFilterModel] = React.useState(
    pythonFilterModel || { items: [] }
  );

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
    effectiveProps.filterModel = localFilterModel;

    const singleSelectFields = new Set(
      (effectiveProps.columns || [])
        .filter((c) => c.type === "singleSelect")
        .map((c) => c.field)
    );

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

  if (props.pagination === false && _muiPatchActive) {
    const fallback = () => {
      _dgLog(log, "WARN: falling back to paginated mode (patch failed)");
      const safeProps = _buildGridProps(props, false);
      return React.createElement(MuiDataGrid_, { ...safeProps, ref });
    };
    return React.createElement(
      MuiThemeProvider_,
      { theme: _muiDefaultTheme },
      React.createElement(
        "div",
        { ref: containerRef, style: { width: "100%", height: "100%" } },
        React.createElement(_DataGridGuard, { fallback: fallback }, grid)
      )
    );
  }

  return React.createElement(
    MuiThemeProvider_,
    { theme: _muiDefaultTheme },
    React.createElement(
      "div",
      { ref: containerRef, style: { width: "100%", height: "100%" } },
      grid
    )
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

    library: str = "@mui/x-data-grid@^8.27.0"
    tag: str = "UnlimitedDataGrid"
    is_default: bool = False

    lib_dependencies: list[str] = [
        "@mui/material@^7.0.0",
        "@emotion/react@^11.14.0",
        "@emotion/styled@^11.14.0",
        "react-plotly.js@^2.6.0",
        "plotly.js-dist-min@^3.0.0",
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
                rx.ImportVar(tag="DataGrid", alias="MuiDataGrid_", install=False),
                rx.ImportVar(
                    tag="GridSignature",
                    alias="GridSignature_",
                    install=False,
                ),
                rx.ImportVar(
                    tag="useGridApiContext",
                    alias="useGridApiContext_",
                    install=False,
                ),
                rx.ImportVar(
                    tag="useGridRootProps",
                    alias="useGridRootProps_",
                    install=False,
                ),
                rx.ImportVar(
                    tag="GridFilterPanel",
                    alias="GridFilterPanel_",
                    install=False,
                ),
            ],
            "@mui/material": [
                rx.ImportVar(tag="createTheme", alias="createTheme_"),
                rx.ImportVar(tag="ThemeProvider", alias="MuiThemeProvider_"),
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
    row_selection_model: rx.Var[dict[str, Any]]

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

    # ---- row detail panel ----
    detail_columns: rx.Var[list[str]]
    detail_height: rx.Var[int]
    detail_labels: rx.Var[dict[str, str]]
    detail_badge_fields: rx.Var[list[str]]
    detail_badge_colors: rx.Var[dict[str, list[str]]]
    detail_renderers: rx.Var[dict[str, Any]]

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
    on_column_visibility_model_change: rx.EventHandler[
        _on_column_visibility_model_change_spec
    ]
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
            import json

            props["get_row_id"] = rx.Var(f"(row) => row[{json.dumps(row_id_field)}]")
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
        props.setdefault(
            "autosize_options",
            {
                "includeHeaders": True,
                "includeOutliers": True,
                "expand": True,
            },
        )

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
                props["slot_props"] = {
                    **existing,
                    "columnMenu": default_slots["columnMenu"],
                }

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
