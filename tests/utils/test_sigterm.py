"""``execsql.utils.sigterm``: the CLI's SIGTERM handler and ``sigterm_held``.

The handler is called directly, so these run on every platform; a real
signal is sent in ``tests/cli/test_sigterm.py``.
"""

from __future__ import annotations

import signal
from unittest.mock import MagicMock

import pytest

import execsql.state as _state
from execsql.utils.sigterm import sigterm_held, terminate


@pytest.fixture
def exec_log():
    _state.exec_log = MagicMock()
    return _state.exec_log


def test_a_sigterm_ends_the_run_at_once(exec_log):
    with pytest.raises(SystemExit) as exc:
        terminate(signal.SIGTERM, None)
    assert exc.value.code == 128 + signal.SIGTERM
    exec_log.log_exit_terminated.assert_called_once_with()


def test_a_held_sigterm_ends_the_run_when_the_block_ends(exec_log):
    done = []
    with pytest.raises(SystemExit) as exc, sigterm_held():
        terminate(signal.SIGTERM, None)
        done.append("rest of the block")
    assert done == ["rest of the block"]
    assert exc.value.code == 128 + signal.SIGTERM
    exec_log.log_exit_terminated.assert_called_once_with()


def test_nested_blocks_act_on_it_when_the_outermost_ends(exec_log):
    done = []
    with pytest.raises(SystemExit), sigterm_held():
        with sigterm_held():
            terminate(signal.SIGTERM, None)
        done.append("after the inner block")
    assert done == ["after the inner block"]


def test_a_held_sigterm_wins_over_the_blocks_exception(exec_log):
    with pytest.raises(SystemExit) as exc, sigterm_held():
        terminate(signal.SIGTERM, None)
        raise FileNotFoundError("no such command")
    assert isinstance(exc.value.__context__, FileNotFoundError)


def test_a_block_without_a_sigterm_changes_nothing(exec_log):
    with sigterm_held():
        pass
    with pytest.raises(ValueError), sigterm_held():
        raise ValueError
    exec_log.log_exit_terminated.assert_not_called()
    with pytest.raises(SystemExit):
        terminate(signal.SIGTERM, None)
