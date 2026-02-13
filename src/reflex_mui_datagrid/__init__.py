"""reflex-mui-datagrid – Reflex wrapper for MUI X DataGrid v8.

Install the base package for the DataGrid component and polars LazyFrame support::

    pip install reflex-mui-datagrid

Install with the ``[bio]`` extra for polars-bio integration (auto-extracts
VCF/BAM column descriptions from file headers)::

    pip install reflex-mui-datagrid[bio]
"""

from reflex_mui_datagrid.datagrid import DataGrid, DataGridNamespace, WrappedDataGrid, data_grid
from reflex_mui_datagrid.models import ColumnDef
from reflex_mui_datagrid.polars_utils import lazyframe_to_datagrid, polars_dtype_to_grid_type, show_dataframe

# Optional polars-bio integration – available when installed with [bio] extra.
try:
    from reflex_mui_datagrid.polars_bio_utils import (
        bio_lazyframe_to_datagrid,
        extract_vcf_descriptions,
    )
except ImportError:
    pass
