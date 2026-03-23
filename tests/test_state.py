"""
Tests for execsql.state — global runtime state and utility functions.

Covers: version variables, compiled regex defaults, mutable state defaults,
and the endloop() utility function.  xcmd_test() is not covered here because
it requires the full metacommand dispatch table (conditionallist) to be loaded,
which only happens inside main().
"""

from __future__ import annotations

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.script import CommandList


# ---------------------------------------------------------------------------
# Version variables
# ---------------------------------------------------------------------------


class TestVersionVars:
    def test_primary_vno_is_int(self):
        assert isinstance(_state.primary_vno, int)

    def test_secondary_vno_is_int(self):
        assert isinstance(_state.secondary_vno, int)

    def test_tertiary_vno_is_int(self):
        assert isinstance(_state.tertiary_vno, int)

    def test_version_nonnegative(self):
        assert _state.primary_vno >= 0
        assert _state.secondary_vno >= 0
        assert _state.tertiary_vno >= 0

    def test_primary_vno_matches_package(self):
        from execsql import __version__

        parts = __version__.split(".")
        assert _state.primary_vno == int(parts[0])


# ---------------------------------------------------------------------------
# Compiled regex defaults
# ---------------------------------------------------------------------------


class TestGlobalRegexDefaults:
    def test_varlike_matches_dollar_var(self):
        assert _state.varlike.search("!!$MYVAR!!")

    def test_varlike_matches_at_var(self):
        assert _state.varlike.search("!!@counter!!")

    def test_varlike_matches_amp_var(self):
        assert _state.varlike.search("!!&ENVVAR!!")

    def test_varlike_no_match_plain_text(self):
        assert not _state.varlike.search("just plain text")

    def test_varlike_case_insensitive(self):
        assert _state.varlike.search("!!$myvar!!")

    def test_defer_rx_matches_deferred_var(self):
        m = _state.defer_rx.search("!{$somevar}!")
        assert m is not None

    def test_defer_rx_captures_full_expr(self):
        m = _state.defer_rx.search("prefix !{$foo}! suffix")
        assert m.group(1) == "!{$foo}!"

    def test_defer_rx_no_match_plain(self):
        assert not _state.defer_rx.search("no deferred here")

    def test_endloop_rx_matches_end_loop(self):
        assert _state.endloop_rx.match("END LOOP")

    def test_endloop_rx_matches_lowercase(self):
        assert _state.endloop_rx.match("end loop")

    def test_endloop_rx_matches_with_spaces(self):
        assert _state.endloop_rx.match("  END  LOOP  ")

    def test_endloop_rx_no_match_partial(self):
        assert not _state.endloop_rx.match("END LOOP EXTRA")

    def test_loop_rx_matches_loop_keyword(self):
        assert _state.loop_rx.search("  LOOP 5 TIMES")

    def test_loop_rx_case_insensitive(self):
        assert _state.loop_rx.search("loop 10 TIMES")


# ---------------------------------------------------------------------------
# Mutable state defaults
# ---------------------------------------------------------------------------


class TestMutableStateDefaults:
    def test_compiling_loop_is_false(self):
        # Only valid when no loop is being compiled; at module level this is False.
        assert _state.compiling_loop is False

    def test_stringtypes_is_str(self):
        assert _state.stringtypes is str

    def test_loop_nest_level_is_int(self):
        assert isinstance(_state.loop_nest_level, int)

    def test_cmds_run_is_int(self):
        assert isinstance(_state.cmds_run, int)

    def test_commandliststack_is_list(self):
        assert isinstance(_state.commandliststack, list)

    def test_savedscripts_is_dict(self):
        assert isinstance(_state.savedscripts, dict)

    def test_loopcommandstack_is_list(self):
        assert isinstance(_state.loopcommandstack, list)

    def test_logfile_encoding_is_utf8(self):
        assert _state.logfile_encoding == "utf8"


# ---------------------------------------------------------------------------
# endloop()
# ---------------------------------------------------------------------------


class TestEndloop:
    def test_endloop_raises_erinfo_when_stack_empty(self):
        """endloop() raises ErrInfo when loopcommandstack is empty."""
        saved = list(_state.loopcommandstack)
        _state.loopcommandstack.clear()
        try:
            with pytest.raises(ErrInfo):
                _state.endloop()
        finally:
            _state.loopcommandstack.extend(saved)

    def test_endloop_moves_commandlist_to_exec_stack(self):
        """endloop() pops loopcommandstack and appends to commandliststack."""
        cl = CommandList([], "test_loop")
        saved_loop = list(_state.loopcommandstack)
        saved_cmd = list(_state.commandliststack)
        _state.loopcommandstack.clear()
        _state.commandliststack.clear()

        _state.loopcommandstack.append(cl)
        _state.compiling_loop = True

        try:
            _state.endloop()
            assert len(_state.commandliststack) == 1
            assert _state.commandliststack[0] is cl
            assert len(_state.loopcommandstack) == 0
            assert _state.compiling_loop is False
        finally:
            _state.loopcommandstack.clear()
            _state.loopcommandstack.extend(saved_loop)
            _state.commandliststack.clear()
            _state.commandliststack.extend(saved_cmd)
            _state.compiling_loop = False

    def test_endloop_handles_nested_loops(self):
        """With two entries on loopcommandstack, only the top is popped."""
        cl1 = CommandList([], "outer_loop")
        cl2 = CommandList([], "inner_loop")
        saved_loop = list(_state.loopcommandstack)
        saved_cmd = list(_state.commandliststack)
        _state.loopcommandstack.clear()
        _state.commandliststack.clear()

        _state.loopcommandstack.extend([cl1, cl2])
        _state.compiling_loop = True

        try:
            _state.endloop()
            assert len(_state.loopcommandstack) == 1
            assert _state.loopcommandstack[0] is cl1
            assert _state.commandliststack[-1] is cl2
        finally:
            _state.loopcommandstack.clear()
            _state.loopcommandstack.extend(saved_loop)
            _state.commandliststack.clear()
            _state.commandliststack.extend(saved_cmd)
            _state.compiling_loop = False
