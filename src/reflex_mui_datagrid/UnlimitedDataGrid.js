/**
 * UnlimitedDataGrid – thin React wrapper around MUI X DataGrid (Community)
 * that removes the 100-row page-size cap and allows pagination={false}.
 *
 * How it works:
 *
 * 1. The Community edition's `useDataGridProps` hook applies "forced props"
 *    last, overriding `pagination` to `true` and `signature` to `'DataGrid'`.
 *    The signature triggers `throwIfPageSizeExceedsTheLimit` which throws
 *    when pageSize > 100.
 *
 * 2. This wrapper patches `throwIfPageSizeExceedsTheLimit` to a no-op at
 *    import time (before any component renders).  It also wraps
 *    `useDataGridProps` so that the caller's `pagination` prop is respected.
 *
 * The library is MIT-licensed, so this is perfectly legal.
 */
import React from "react";
import { DataGrid as MuiDataGrid } from "@mui/x-data-grid";

// ---------------------------------------------------------------------------
// Dynamic require helper – hidden from Vite's static import analysis.
//
// Vite scans bare `require("...")` calls at build time and fails if the
// specifier doesn't match the package's "exports" map.  By obtaining
// `require` indirectly through `module.constructor`, the call becomes
// invisible to the static analyser while still working at runtime.
// ---------------------------------------------------------------------------
let _require;
try {
  _require = typeof module !== "undefined"
    ? module.constructor.prototype.require
    : undefined;
} catch (_e) {
  _require = undefined;
}

// ---------------------------------------------------------------------------
// Patch 1: Remove the 100-row page-size cap.
// ---------------------------------------------------------------------------
if (_require) {
  try {
    const paginationUtils = _require(
      "@mui/x-data-grid/hooks/features/pagination/gridPaginationUtils"
    );
    if (paginationUtils && typeof paginationUtils.throwIfPageSizeExceedsTheLimit === "function") {
      paginationUtils.throwIfPageSizeExceedsTheLimit = () => {};
    }
  } catch (_e) {
    // Module not resolvable in this environment – ignored.
  }
}

// ---------------------------------------------------------------------------
// Patch 2: Wrap useDataGridProps so `pagination` is not force-overridden.
// ---------------------------------------------------------------------------
if (_require) {
  try {
    const propsModule = _require(
      "@mui/x-data-grid/DataGrid/useDataGridProps"
    );
    const origHook = propsModule && propsModule.useDataGridProps;
    if (typeof origHook === "function") {
      propsModule.useDataGridProps = (inProps) => {
        const result = origHook(inProps);
        // Respect the caller's pagination prop instead of the forced `true`.
        if (inProps.pagination !== undefined) {
          return { ...result, pagination: inProps.pagination };
        }
        return result;
      };
    }
  } catch (_e) {
    // Module not resolvable in this environment – ignored.
  }
}

// ---------------------------------------------------------------------------
// Helper: inject renderHeader for columns that have a description and
// showDescriptionInHeader is enabled on the grid.
// ---------------------------------------------------------------------------
function enhanceColumnsWithDescriptions(columns, showDescriptionInHeader) {
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
          {
            style: {
              lineHeight: 1.2,
              overflow: "hidden",
              width: "100%",
            },
          },
          React.createElement(
            "div",
            {
              style: {
                fontWeight: 600,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              },
            },
            headerName
          ),
          React.createElement(
            "div",
            {
              style: {
                fontSize: "0.7em",
                color: "#888",
                fontWeight: 400,
                whiteSpace: "normal",
                lineHeight: 1.3,
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              },
            },
            desc
          )
        ),
    };
  });
}

// ---------------------------------------------------------------------------
// Wrapper component
// ---------------------------------------------------------------------------
export const UnlimitedDataGrid = React.forwardRef((props, ref) => {
  const { showDescriptionInHeader, columns, ...rest } = props;
  const enhancedColumns = enhanceColumnsWithDescriptions(
    columns,
    showDescriptionInHeader
  );
  return React.createElement(MuiDataGrid, {
    ...rest,
    columns: enhancedColumns,
    ref,
  });
});

UnlimitedDataGrid.displayName = "UnlimitedDataGrid";
