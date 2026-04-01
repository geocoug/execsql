"""
Tests for execsql.state — global runtime state and utility functions.

Covers: version variables, compiled regex defaults, mutable state defaults,
the endloop() utility function, and the RuntimeContext / module proxy.
xcmd_test() is not covered here because it requires the full metacommand
dispatch table (conditionallist) to be loaded, which only happens inside main().
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.script import CommandList
from execsql.state import RuntimeContext, _CONTEXT_ATTRS


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


# ---------------------------------------------------------------------------
# RuntimeContext and module proxy
# ---------------------------------------------------------------------------


class TestRuntimeContext:
    def test_get_context_returns_runtime_context(self):
        ctx = _state.get_context()
        assert isinstance(ctx, RuntimeContext)

    def test_context_attrs_matches_slots(self):
        """_CONTEXT_ATTRS and RuntimeContext.__slots__ must stay in sync."""
        assert set(RuntimeContext.__slots__) == _CONTEXT_ATTRS

    def test_runtime_context_defaults(self):
        """A fresh RuntimeContext has the expected initial values."""
        ctx = RuntimeContext()
        assert ctx.conf is None
        assert ctx.logfile_encoding == "utf8"
        assert ctx.compiling_loop is False
        assert ctx.loop_nest_level == 0
        assert ctx.cmds_run == 0
        assert ctx.commandliststack == []
        assert ctx.savedscripts == {}
        assert ctx.loopcommandstack == []
        assert ctx.subvars is None
        assert ctx.dbs is None
        assert ctx.filewriter is None

    def test_set_context_swaps_state(self):
        """set_context() makes _state.foo resolve against the new context."""
        original = _state.get_context()
        new_ctx = RuntimeContext()
        sentinel = object()
        new_ctx.upass = sentinel

        try:
            _state.set_context(new_ctx)
            assert _state.upass is sentinel
            assert _state.get_context() is new_ctx
        finally:
            _state.set_context(original)

    def test_proxy_read_write_roundtrip(self):
        """Writing via _state.foo = val and reading via _state.foo works."""
        original = _state.upass
        try:
            _state.upass = "test_password"
            assert _state.upass == "test_password"
            assert _state.get_context().upass == "test_password"
        finally:
            _state.upass = original

    def test_proxy_hasattr(self):
        """hasattr works for both context attrs and module-level constants."""
        assert hasattr(_state, "conf")
        assert hasattr(_state, "commandliststack")
        assert hasattr(_state, "varlike")
        assert hasattr(_state, "primary_vno")
        assert not hasattr(_state, "nonexistent_attr_xyz")

    def test_proxy_dir_includes_context_attrs(self):
        """dir(_state) includes context attributes."""
        d = dir(_state)
        assert "conf" in d
        assert "commandliststack" in d
        assert "varlike" in d

    def test_reset_preserves_filewriter(self):
        """reset() keeps filewriter alive (atexit-managed subprocess)."""
        sentinel = object()
        _state.filewriter = sentinel
        try:
            _state.reset()
            assert _state.filewriter is sentinel
        finally:
            _state.filewriter = None

    def test_reset_closes_databases(self):
        """reset() calls dbs.closeall() before discarding the pool."""
        mock_dbs = MagicMock()
        _state.dbs = mock_dbs
        _state.reset()
        mock_dbs.closeall.assert_called_once()
        assert _state.dbs is None

    def test_reset_produces_clean_defaults(self):
        """After reset(), all context attrs are at their default values."""
        _state.compiling_loop = True
        _state.cmds_run = 42
        _state.upass = "stale"
        _state.reset()
        assert _state.compiling_loop is False
        assert _state.cmds_run == 0
        assert _state.upass is None

    def test_slots_prevent_typo_attrs(self):
        """RuntimeContext.__slots__ prevents setting misspelled attributes."""
        ctx = RuntimeContext()
        with pytest.raises(AttributeError):
            ctx.conff = "typo"  # noqa: B009
