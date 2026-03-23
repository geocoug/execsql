from __future__ import annotations

"""
Feather and Parquet import for execsql.

Provides :func:`import_feather` (Apache Arrow Feather v2 via ``pyarrow``)
and :func:`import_parquet` (Parquet format via ``pyarrow``), used by
``IMPORT … FORMAT feather`` and ``FORMAT parquet``.
"""

import os
from typing import Any, Optional

from execsql.exceptions import ErrInfo
from execsql.db.base import Database
from execsql.importers.base import import_data_table


def import_feather(
    db: Database,
    schemaname: Optional[str],
    tablename: str,
    filename: str,
    is_new: Any,
) -> None:
    from execsql.utils.errors import exception_info

    try:
        import numpy as np
        import pandas as pd
        import pyarrow.feather
    except Exception:
        raise ErrInfo(
            "exception",
            exception_msg=exception_info(),
            other_msg="The pandas and pyarrow Python libraries must be installed to import data from the Feather format.",
        )
    df = pd.read_feather(filename)
    df = df.replace({np.nan: None})
    hdrs = df.columns.values.tolist()
    data = df.values.tolist()
    import_data_table(db, schemaname, tablename, is_new, hdrs, data)


def import_parquet(
    db: Database,
    schemaname: Optional[str],
    tablename: str,
    filename: str,
    is_new: Any,
) -> None:
    from execsql.utils.errors import exception_info

    try:
        import numpy as np
        import pandas as pd
    except Exception:
        raise ErrInfo(
            "exception",
            exception_msg=exception_info(),
            other_msg="The pandas and fastparquet or pyarrow Python libraries must be installed to import data from the Parquet format.",
        )
    df = pd.read_parquet(filename)
    df = df.replace({np.nan: None})
    hdrs = df.columns.values.tolist()
    data = df.values.tolist()
    import_data_table(db, schemaname, tablename, is_new, hdrs, data)
