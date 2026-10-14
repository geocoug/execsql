"""Helpers shared by the metacommand tests."""

from __future__ import annotations

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.utils.fileio import filewriter_close_all_after_write


def flush_filewriter() -> None:
    """Wait until the run's file writer has written and closed every file, as a run does before it returns.

    A run that halted has already stopped its writer, which wrote everything first.
    """
    writer = _state.filewriter
    if writer is None or not writer.is_alive():
        return
    try:
        filewriter_close_all_after_write()
    except ErrInfo:
        if writer.is_alive():
            raise  # output really was lost; a writer that stopped meanwhile had flushed already
