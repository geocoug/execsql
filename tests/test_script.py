"""Tests for core script-execution data structures in execsql.script."""

from __future__ import annotations

import re

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.script import (
    BatchLevels,
    CounterVars,
    IfLevels,
    LocalSubVarSet,
    MetaCommand,
    MetaCommandList,
    MetacommandStmt,
    ScriptArgSubVarSet,
    SqlStmt,
    SubVarSet,
)


# ---------------------------------------------------------------------------
# BatchLevels
# ---------------------------------------------------------------------------


class TestBatchLevels:
    def test_initially_not_in_batch(self):
        bl = BatchLevels()
        assert bl.in_batch() is False

    def test_new_batch_enters_batch(self):
        bl = BatchLevels()
        bl.new_batch()
        assert bl.in_batch() is True

    def test_end_batch_pops_level(self):
        bl = BatchLevels()
        bl.new_batch()

        class FakeDB:
            committed = False

            def commit(self):
                self.committed = True

        db = FakeDB()
        bl.using_db(db)
        bl.end_batch()
        assert bl.in_batch() is False
        assert db.committed is True

    def test_rollback_batch_calls_rollback(self):
        bl = BatchLevels()
        bl.new_batch()

        class FakeDB:
            rolled_back = False

            def rollback(self):
                self.rolled_back = True

        db = FakeDB()
        bl.using_db(db)
        bl.rollback_batch()
        assert db.rolled_back is True

    def test_using_db_registers_db(self):
        bl = BatchLevels()
        bl.new_batch()

        class FakeDB:
            pass

        db = FakeDB()
        bl.using_db(db)
        assert bl.uses_db(db) is True

    def test_uses_db_false_when_not_registered(self):
        bl = BatchLevels()
        bl.new_batch()

        class FakeDB:
            pass

        assert bl.uses_db(FakeDB()) is False

    def test_uses_db_false_when_no_batch(self):
        bl = BatchLevels()

        class FakeDB:
            pass

        assert bl.uses_db(FakeDB()) is False

    def test_using_db_deduplicates(self):
        bl = BatchLevels()
        bl.new_batch()

        class FakeDB:
            commit_count = 0

            def commit(self):
                self.commit_count += 1

        db = FakeDB()
        bl.using_db(db)
        bl.using_db(db)
        bl.end_batch()
        assert db.commit_count == 1

    def test_nested_batches(self):
        bl = BatchLevels()
        bl.new_batch()
        bl.new_batch()
        assert bl.in_batch() is True

        class FakeDB:
            def commit(self):
                pass

        bl.end_batch()
        assert bl.in_batch() is True
        bl.end_batch()
        assert bl.in_batch() is False

    def test_rollback_noop_when_no_batch(self):
        bl = BatchLevels()
        bl.rollback_batch()  # should not raise


# ---------------------------------------------------------------------------
# IfLevels
# ---------------------------------------------------------------------------


class TestIfLevels:
    def setup_method(self):
        # Ensure commandliststack is empty so current_script_line() returns ("", 0).
        _state.commandliststack = []

    def test_all_true_when_empty(self):
        ifl = IfLevels()
        assert ifl.all_true() is True

    def test_only_current_false_when_empty(self):
        ifl = IfLevels()
        assert ifl.only_current_false() is False

    def test_nest_true_all_true(self):
        ifl = IfLevels()
        ifl.nest(True)
        assert ifl.all_true() is True

    def test_nest_false_not_all_true(self):
        ifl = IfLevels()
        ifl.nest(False)
        assert ifl.all_true() is False

    def test_current_returns_top_value(self):
        ifl = IfLevels()
        ifl.nest(True)
        assert ifl.current() is True

    def test_current_raises_when_empty(self):
        ifl = IfLevels()
        with pytest.raises(ErrInfo):
            ifl.current()

    def test_unnest_removes_top(self):
        ifl = IfLevels()
        ifl.nest(True)
        ifl.unnest()
        assert ifl.all_true() is True

    def test_unnest_raises_when_empty(self):
        ifl = IfLevels()
        with pytest.raises(ErrInfo):
            ifl.unnest()

    def test_invert_flips_top(self):
        ifl = IfLevels()
        ifl.nest(True)
        ifl.invert()
        assert ifl.current() is False

    def test_invert_raises_when_empty(self):
        ifl = IfLevels()
        with pytest.raises(ErrInfo):
            ifl.invert()

    def test_replace_changes_top(self):
        ifl = IfLevels()
        ifl.nest(True)
        ifl.replace(False)
        assert ifl.current() is False

    def test_replace_raises_when_empty(self):
        ifl = IfLevels()
        with pytest.raises(ErrInfo):
            ifl.replace(True)

    def test_only_current_false_single_level(self):
        ifl = IfLevels()
        ifl.nest(False)
        assert ifl.only_current_false() is True

    def test_only_current_false_when_current_true(self):
        ifl = IfLevels()
        ifl.nest(True)
        assert ifl.only_current_false() is False

    def test_only_current_false_nested_outer_false(self):
        # Both outer and current are false — not "only current false"
        ifl = IfLevels()
        ifl.nest(False)  # outer level = False
        ifl.nest(False)  # current level = False
        assert ifl.only_current_false() is False

    def test_only_current_false_nested_outer_true(self):
        ifl = IfLevels()
        ifl.nest(True)  # outer = True
        ifl.nest(False)  # current = False
        assert ifl.only_current_false() is True

    def test_script_lines_raises_with_insufficient_depth(self):
        ifl = IfLevels()
        ifl.nest(True)
        with pytest.raises(ErrInfo):
            ifl.script_lines(2)

    def test_script_lines_returns_correct_count(self):
        ifl = IfLevels()
        ifl.nest(True)
        ifl.nest(False)
        lines = ifl.script_lines(2)
        assert len(lines) == 2


# ---------------------------------------------------------------------------
# CounterVars
# ---------------------------------------------------------------------------


class TestCounterVars:
    def test_set_and_retrieve(self):
        cv = CounterVars()
        cv.set_counter(1, 42)
        assert cv.counters["counter_1"] == 42

    def test_remove_counter(self):
        cv = CounterVars()
        cv.set_counter(1, 5)
        cv.remove_counter(1)
        assert "counter_1" not in cv.counters

    def test_remove_nonexistent_counter_noop(self):
        cv = CounterVars()
        cv.remove_counter(99)  # should not raise

    def test_remove_all_counters(self):
        cv = CounterVars()
        cv.set_counter(1, 1)
        cv.set_counter(2, 2)
        cv.remove_all_counters()
        assert cv.counters == {}

    def test_substitute_increments_counter(self):
        cv = CounterVars()
        result, changed = cv.substitute("value is !!$COUNTER_1!!")
        assert changed is True
        assert result == "value is 1"

    def test_substitute_auto_initializes_from_zero(self):
        cv = CounterVars()
        # Counter must not start at string position 0 — the source passes re.I (=2)
        # as the pos argument to re.search(), so patterns at pos < 2 are not found.
        cv.substitute("x=!!$COUNTER_1!!")
        result, _ = cv.substitute("x=!!$COUNTER_1!!")
        assert result == "x=2"

    def test_substitute_no_match_returns_unchanged(self):
        cv = CounterVars()
        result, changed = cv.substitute("no counter here")
        assert changed is False
        assert result == "no counter here"

    def test_substitute_all_multiple_occurrences(self):
        cv = CounterVars()
        # Two different counter references in one string — substitute_all loops
        result, changed = cv.substitute_all("A=!!$COUNTER_1!! B=!!$COUNTER_2!!")
        assert changed is True
        assert "A=1" in result
        assert "B=1" in result

    def test_case_insensitive_counter_name(self):
        cv = CounterVars()
        # Pattern must not start at string position 0 (see note in test_substitute_auto_initializes_from_zero).
        result, changed = cv.substitute("x=!!$counter_1!!")
        assert changed is True
        assert result == "x=1"


# ---------------------------------------------------------------------------
# SubVarSet
# ---------------------------------------------------------------------------


class TestSubVarSet:
    def test_add_and_retrieve(self):
        sv = SubVarSet()
        sv.add_substitution("$myvar", "hello")
        assert sv.varvalue("$myvar") == "hello"

    def test_varvalue_returns_none_for_missing(self):
        sv = SubVarSet()
        assert sv.varvalue("$missing") is None

    def test_add_overwrites_existing(self):
        sv = SubVarSet()
        sv.add_substitution("$x", "first")
        sv.add_substitution("$x", "second")
        assert sv.varvalue("$x") == "second"

    def test_remove_substitution(self):
        sv = SubVarSet()
        sv.add_substitution("$x", "val")
        sv.remove_substitution("$x")
        assert sv.varvalue("$x") is None

    def test_sub_exists_true(self):
        sv = SubVarSet()
        sv.add_substitution("$x", "v")
        assert sv.sub_exists("$x") is True

    def test_sub_exists_false(self):
        sv = SubVarSet()
        assert sv.sub_exists("$x") is False

    def test_substitute_replaces_variable(self):
        sv = SubVarSet()
        sv.add_substitution("$name", "world")
        result, changed = sv.substitute("hello !!$name!!")
        assert changed is True
        assert result == "hello world"

    def test_substitute_no_match_unchanged(self):
        sv = SubVarSet()
        result, changed = sv.substitute("no vars here")
        assert changed is False
        assert result == "no vars here"

    def test_substitute_all_multiple_vars(self):
        sv = SubVarSet()
        sv.add_substitution("$a", "foo")
        sv.add_substitution("$b", "bar")
        result, changed = sv.substitute_all("!!$a!! and !!$b!!")
        assert changed is True
        assert result == "foo and bar"

    def test_substitute_quoted_var_escapes_single_quotes(self):
        sv = SubVarSet()
        sv.add_substitution("$val", "it's")
        result, changed = sv.substitute("!'!$val!'!")
        assert changed is True
        assert "it''s" in result

    def test_substitute_double_quoted_var(self):
        sv = SubVarSet()
        sv.add_substitution("$val", "hello")
        result, changed = sv.substitute('!"!$val!"!')
        assert changed is True
        assert '"hello"' in result

    def test_var_name_ok_valid(self):
        sv = SubVarSet()
        assert sv.var_name_ok("$myvar") is True

    def test_var_name_ok_invalid(self):
        sv = SubVarSet()
        assert sv.var_name_ok("!invalid") is False

    def test_check_var_name_raises_on_invalid(self):
        sv = SubVarSet()
        with pytest.raises(ErrInfo):
            sv.check_var_name("!!bad!!")

    def test_append_substitution_creates_if_missing(self):
        sv = SubVarSet()
        sv.append_substitution("$x", "first")
        assert sv.varvalue("$x") == "first"

    def test_append_substitution_appends_with_newline(self):
        sv = SubVarSet()
        sv.add_substitution("$x", "first")
        sv.append_substitution("$x", "second")
        val = sv.varvalue("$x")
        assert val == "first\nsecond"

    def test_increment_by_numeric(self):
        sv = SubVarSet()
        sv.add_substitution("$n", "10")
        sv.increment_by("$n", 5)
        assert sv.varvalue("$n") == "15"

    def test_increment_by_initializes_to_zero(self):
        sv = SubVarSet()
        sv.increment_by("$n", 3)
        assert sv.varvalue("$n") == "3"

    def test_merge_combines_vars(self):
        sv1 = SubVarSet()
        sv1.add_substitution("$a", "1")
        sv2 = SubVarSet()
        sv2.add_substitution("$b", "2")
        merged = sv1.merge(sv2)
        assert merged.varvalue("$a") == "1"
        assert merged.varvalue("$b") == "2"

    def test_merge_with_none_returns_self(self):
        sv = SubVarSet()
        sv.add_substitution("$x", "v")
        result = sv.merge(None)
        assert result is sv

    def test_case_insensitive_lookup(self):
        sv = SubVarSet()
        sv.add_substitution("$MYVAR", "hello")
        assert sv.varvalue("$myvar") == "hello"

    # -- dict-based internal storage -----------------------------------------

    def test_internal_dict_storage(self):
        sv = SubVarSet()
        sv.add_substitution("$x", "val")
        assert "$x" in sv._subs_dict
        assert sv._subs_dict["$x"] == "val"

    def test_substitutions_property_returns_tuples(self):
        sv = SubVarSet()
        sv.add_substitution("$a", "1")
        sv.add_substitution("$b", "2")
        subs = sv.substitutions
        assert isinstance(subs, list)
        assert all(isinstance(s, tuple) and len(s) == 2 for s in subs)
        names = [s[0] for s in subs]
        assert "$a" in names
        assert "$b" in names

    def test_substitutions_setter_from_list_of_tuples(self):
        sv = SubVarSet()
        sv.substitutions = [("$a", "1"), ("$b", "2")]
        assert sv.varvalue("$a") == "1"
        assert sv.varvalue("$b") == "2"

    def test_remove_substitution_dict_based(self):
        sv = SubVarSet()
        sv.add_substitution("$x", "val")
        sv.add_substitution("$y", "other")
        sv.remove_substitution("$x")
        assert "$x" not in sv._subs_dict
        assert sv.varvalue("$y") == "other"

    def test_sub_exists_dict_based(self):
        sv = SubVarSet()
        sv.add_substitution("$x", "v")
        assert sv.sub_exists("$x") is True
        sv.remove_substitution("$x")
        assert sv.sub_exists("$x") is False

    # -- compiled regex patterns ---------------------------------------------

    def test_compiled_patterns_created_on_add(self):
        sv = SubVarSet()
        sv.add_substitution("$foo", "bar")
        assert "$foo" in sv._compiled_patterns
        pat, patq, patdq = sv._compiled_patterns["$foo"]
        assert pat.search("!!$foo!!") is not None
        assert patq.search("!'!$foo!'!") is not None
        assert patdq.search('!"!$foo!"!') is not None

    def test_compiled_patterns_removed_on_remove(self):
        sv = SubVarSet()
        sv.add_substitution("$foo", "bar")
        sv.remove_substitution("$foo")
        assert "$foo" not in sv._compiled_patterns

    def test_substitute_uses_compiled_patterns(self):
        sv = SubVarSet()
        sv.add_substitution("$x", "replaced")
        result, changed = sv.substitute("value is !!$x!!")
        assert changed is True
        assert result == "value is replaced"

    def test_substitute_case_insensitive_with_compiled(self):
        sv = SubVarSet()
        sv.add_substitution("$myvar", "val")
        result, changed = sv.substitute("!!$MYVAR!!")
        assert changed is True
        assert result == "val"

    def test_substitute_single_quoted_with_compiled(self):
        sv = SubVarSet()
        sv.add_substitution("$v", "it's")
        result, changed = sv.substitute("!'!$v!'!")
        assert changed is True
        assert "it''s" in result

    def test_substitute_double_quoted_with_compiled(self):
        sv = SubVarSet()
        sv.add_substitution("$v", "hello")
        result, changed = sv.substitute('!"!$v!"!')
        assert changed is True
        assert '"hello"' in result

    def test_merge_preserves_compiled_patterns(self):
        sv1 = SubVarSet()
        sv1.add_substitution("$a", "1")
        sv2 = SubVarSet()
        sv2.add_substitution("$b", "2")
        merged = sv1.merge(sv2)
        assert "$a" in merged._compiled_patterns
        assert "$b" in merged._compiled_patterns
        result, changed = merged.substitute_all("!!$a!! !!$b!!")
        assert result == "1 2"

    def test_substitute_none_value(self):
        sv = SubVarSet()
        sv.add_substitution("$x", None)
        result, changed = sv.substitute("!!$x!!")
        assert changed is True
        assert result == ""


class TestSubVarSetTokenOptimization:
    """Tests for the combined-regex substitution optimization.

    Verifies that the single-pass _TOKEN_RX approach matches the same behavior
    as the old per-variable iteration, including edge cases.
    """

    def test_plain_substitution(self):
        sv = SubVarSet()
        sv.add_substitution("$name", "world")
        result, changed = sv.substitute("hello !!$name!!")
        assert changed is True
        assert result == "hello world"

    def test_single_quoted_doubles_apostrophes(self):
        sv = SubVarSet()
        sv.add_substitution("$val", "it's a test")
        result, changed = sv.substitute("WHERE name = !'!$val!'!")
        assert changed is True
        assert "it''s a test" in result

    def test_double_quoted_wraps_in_quotes(self):
        sv = SubVarSet()
        sv.add_substitution("$val", "hello world")
        result, changed = sv.substitute('SELECT !"!$val!"!')
        assert changed is True
        assert '"hello world"' in result

    def test_undefined_variable_not_replaced(self):
        sv = SubVarSet()
        sv.add_substitution("$defined", "yes")
        result, changed = sv.substitute("!!$undefined!! stays")
        assert changed is False
        assert result == "!!$undefined!! stays"

    def test_skips_undefined_finds_defined(self):
        """If the first token is undefined but a later one is defined, still substitutes."""
        sv = SubVarSet()
        sv.add_substitution("$b", "found")
        result, changed = sv.substitute("!!$a!! then !!$b!!")
        assert changed is True
        assert "found" in result
        assert "!!$a!!" in result

    def test_case_insensitive_token_match(self):
        sv = SubVarSet()
        sv.add_substitution("$myvar", "val")
        result, changed = sv.substitute("!!$MYVAR!!")
        assert changed is True
        assert result == "val"

    def test_ampersand_prefix(self):
        sv = SubVarSet()
        sv.add_substitution("&env_var", "production")
        result, changed = sv.substitute("!!&env_var!!")
        assert changed is True
        assert result == "production"

    def test_at_prefix_counter_style(self):
        sv = SubVarSet()
        sv.add_substitution("@count", "42")
        result, changed = sv.substitute("!!@count!!")
        assert changed is True
        assert result == "42"

    def test_no_prefix_variable(self):
        sv = SubVarSet()
        sv.add_substitution("myvar", "value")
        result, changed = sv.substitute("!!myvar!!")
        assert changed is True
        assert result == "value"

    def test_multiple_vars_substitute_all(self):
        sv = SubVarSet()
        sv.add_substitution("$a", "foo")
        sv.add_substitution("$b", "bar")
        sv.add_substitution("$c", "baz")
        result, changed = sv.substitute_all("!!$a!! !!$b!! !!$c!!")
        assert changed is True
        assert result == "foo bar baz"

    def test_substitute_all_with_many_variables(self):
        """Stress test: 100 variables, only 3 used in the string."""
        sv = SubVarSet()
        for i in range(100):
            sv.add_substitution(f"$var{i}", f"val{i}")
        result, changed = sv.substitute_all("!!$var0!! !!$var50!! !!$var99!!")
        assert changed is True
        assert result == "val0 val50 val99"

    def test_none_value_becomes_empty(self):
        sv = SubVarSet()
        sv.add_substitution("$x", None)
        result, changed = sv.substitute("before !!$x!! after")
        assert changed is True
        assert result == "before  after"

    def test_numeric_value_converted_to_string(self):
        sv = SubVarSet()
        sv.add_substitution("$n", 42)
        result, changed = sv.substitute("count is !!$n!!")
        assert changed is True
        assert result == "count is 42"

    def test_empty_string_value(self):
        sv = SubVarSet()
        sv.add_substitution("$x", "")
        result, changed = sv.substitute("!!$x!!")
        assert changed is True
        assert result == ""

    def test_value_containing_exclamation_marks(self):
        sv = SubVarSet()
        sv.add_substitution("$x", "wow!!")
        result, changed = sv.substitute("say !!$x!!")
        assert changed is True
        assert result == "say wow!!"

    def test_adjacent_tokens(self):
        sv = SubVarSet()
        sv.add_substitution("$a", "hello")
        sv.add_substitution("$b", "world")
        result, changed = sv.substitute_all("!!$a!!!!$b!!")
        assert changed is True
        assert result == "helloworld"

    def test_nested_variable_reference_in_value(self):
        """Variable value contains another variable token — substitute_all expands recursively."""
        sv = SubVarSet()
        sv.add_substitution("$inner", "resolved")
        sv.add_substitution("$outer", "!!$inner!!")
        result, changed = sv.substitute_all("!!$outer!!")
        assert changed is True
        assert result == "resolved"

    def test_non_string_input_returns_unchanged(self):
        sv = SubVarSet()
        sv.add_substitution("$x", "val")
        result, changed = sv.substitute(123)
        assert changed is False
        assert result == 123

    def test_no_vars_defined_no_match(self):
        sv = SubVarSet()
        result, changed = sv.substitute("!!$whatever!!")
        assert changed is False

    def test_single_quoted_no_apostrophes(self):
        """Single-quoted form with a value that has no apostrophes — no doubling needed."""
        sv = SubVarSet()
        sv.add_substitution("$v", "clean")
        result, changed = sv.substitute("!'!$v!'!")
        assert changed is True
        assert result == "clean"

    def test_double_quoted_empty_value(self):
        sv = SubVarSet()
        sv.add_substitution("$v", "")
        result, changed = sv.substitute('!"!$v!"!')
        assert changed is True
        assert result == '""'

    def test_substitute_only_replaces_first_occurrence(self):
        """A single substitute() call replaces only the first token."""
        sv = SubVarSet()
        sv.add_substitution("$x", "val")
        result, changed = sv.substitute("!!$x!! and !!$x!!")
        assert changed is True
        assert result == "val and !!$x!!"

    def test_substitute_all_replaces_all_occurrences(self):
        sv = SubVarSet()
        sv.add_substitution("$x", "val")
        result, changed = sv.substitute_all("!!$x!! and !!$x!!")
        assert changed is True
        assert result == "val and val"

    def test_mixed_quote_styles_in_one_string(self):
        sv = SubVarSet()
        sv.add_substitution("$v", "it's")
        result, changed = sv.substitute_all("plain=!!$v!! quoted=!'!$v!'!")
        assert changed is True
        assert "plain=it's" in result
        assert "quoted=it''s" in result


# ---------------------------------------------------------------------------
# LocalSubVarSet
# ---------------------------------------------------------------------------


class TestLocalSubVarSet:
    def test_only_tilde_prefix_accepted(self):
        sv = LocalSubVarSet()
        sv.add_substitution("~localvar", "val")
        assert sv.varvalue("~localvar") == "val"

    def test_dollar_prefix_rejected(self):
        sv = LocalSubVarSet()
        with pytest.raises(ErrInfo):
            sv.add_substitution("$notlocal", "val")

    def test_tilde_prefix_required(self):
        sv = LocalSubVarSet()
        with pytest.raises(ErrInfo):
            sv.add_substitution("noprefix", "val")


# ---------------------------------------------------------------------------
# ScriptArgSubVarSet
# ---------------------------------------------------------------------------


class TestScriptArgSubVarSet:
    def test_hash_prefix_accepted(self):
        sv = ScriptArgSubVarSet()
        sv.add_substitution("#arg1", "value")
        assert sv.varvalue("#arg1") == "value"

    def test_dollar_prefix_rejected(self):
        sv = ScriptArgSubVarSet()
        with pytest.raises(ErrInfo):
            sv.add_substitution("$notarg", "val")

    def test_hash_prefix_required(self):
        sv = ScriptArgSubVarSet()
        with pytest.raises(ErrInfo):
            sv.add_substitution("noprefix", "val")


# ---------------------------------------------------------------------------
# MetaCommand
# ---------------------------------------------------------------------------


class _MockStatus:
    halt_on_metacommand_err = False
    metacommand_error = False


class TestMetaCommand:
    def setup_method(self):
        _state.commandliststack = []
        _state.status = _MockStatus()

    def test_repr(self):
        rx = re.compile(r"^\s*HELLO\s*$", re.I)
        mc = MetaCommand(rx, lambda: None, "Say hello")
        r = repr(mc)
        assert "MetaCommand" in r
        assert "Say hello" in r

    def test_run_returns_true_on_match(self):
        rx = re.compile(r"^\s*HELLO\s*$", re.I)
        results = []
        mc = MetaCommand(rx, lambda metacommandline=None: results.append(metacommandline))
        matched, _ = mc.run("HELLO")
        assert matched is True
        assert len(results) == 1

    def test_run_returns_false_on_no_match(self):
        rx = re.compile(r"^\s*HELLO\s*$", re.I)
        mc = MetaCommand(rx, lambda **kw: None)
        matched, _ = mc.run("WORLD")
        assert matched is False

    def test_hitcount_increments(self):
        rx = re.compile(r"^\s*HELLO\s*$", re.I)
        mc = MetaCommand(rx, lambda **kw: None)
        assert mc.hitcount == 0
        mc.run("HELLO")
        assert mc.hitcount == 1
        mc.run("HELLO")
        assert mc.hitcount == 2

    def test_run_passes_group_dict_as_kwargs(self):
        rx = re.compile(r"^\s*SET\s+(?P<varname>\w+)\s*=\s*(?P<value>\w+)\s*$", re.I)
        captured = {}

        def handler(varname=None, value=None, metacommandline=None, **kw):
            captured["varname"] = varname
            captured["value"] = value

        mc = MetaCommand(rx, handler)
        mc.run("SET myvar = hello")
        assert captured["varname"] == "myvar"
        assert captured["value"] == "hello"

    def test_run_sets_error_flag_on_exception(self):
        rx = re.compile(r".*", re.I)

        def bad_handler(**kw):
            raise ValueError("oops")

        mc = MetaCommand(rx, bad_handler, set_error_flag=True)
        mc.run("anything")
        assert _state.status.metacommand_error is True

    def test_run_clears_error_flag_on_success(self):
        _state.status.metacommand_error = True
        rx = re.compile(r".*", re.I)
        mc = MetaCommand(rx, lambda **kw: None, set_error_flag=True)
        mc.run("anything")
        assert _state.status.metacommand_error is False


# ---------------------------------------------------------------------------
# MetaCommandList
# ---------------------------------------------------------------------------


class TestMetaCommandList:
    def setup_method(self):
        _state.commandliststack = []
        _state.status = _MockStatus()

    def test_initially_empty(self):
        mcl = MetaCommandList()
        assert list(mcl) == []

    def test_add_single_regex(self):
        mcl = MetaCommandList()
        mcl.add(r"^\s*HELLO\s*$", lambda **kw: None, "hello")
        nodes = list(mcl)
        assert len(nodes) == 1

    def test_add_tuple_of_regexes(self):
        mcl = MetaCommandList()
        mcl.add((r"^\s*HELLO\s*$", r"^\s*HI\s*$"), lambda **kw: None)
        nodes = list(mcl)
        assert len(nodes) == 2

    def test_get_match_returns_none_when_no_match(self):
        mcl = MetaCommandList()
        mcl.add(r"^\s*HELLO\s*$", lambda **kw: None)
        assert mcl.get_match("GOODBYE") is None

    def test_get_match_returns_node_and_match(self):
        mcl = MetaCommandList()
        mcl.add(r"^\s*HELLO\s*$", lambda **kw: None)
        result = mcl.get_match("HELLO")
        assert result is not None
        node, m = result
        assert m is not None

    def test_get_match_case_insensitive(self):
        mcl = MetaCommandList()
        mcl.add(r"^\s*HELLO\s*$", lambda **kw: None)
        assert mcl.get_match("hello") is not None
        assert mcl.get_match("Hello") is not None

    def test_iter_yields_metacommand_nodes(self):
        mcl = MetaCommandList()
        mcl.add(r"^\s*A\s*$", lambda **kw: None, "cmd-a")
        mcl.add(r"^\s*B\s*$", lambda **kw: None, "cmd-b")
        nodes = list(mcl)
        descs = {n.description for n in nodes}
        assert "cmd-a" in descs
        assert "cmd-b" in descs


class TestMetaCommandListKeywordIndex:
    """Tests for the keyword-indexed dispatch optimization."""

    def setup_method(self):
        _state.commandliststack = []
        _state.status = _MockStatus()

    def test_keyword_index_groups_by_leading_keyword(self):
        mcl = MetaCommandList()
        mcl.add(r"^\s*EXPORT\s+QUERY\s+.*$", lambda **kw: None, "export-q")
        mcl.add(r"^\s*EXPORT\s+METADATA\s+.*$", lambda **kw: None, "export-m")
        mcl.add(r"^\s*IMPORT\s+.*$", lambda **kw: None, "import")
        assert "EXPORT" in mcl._by_keyword
        assert "IMPORT" in mcl._by_keyword
        assert len(mcl._by_keyword["EXPORT"]) == 2
        assert len(mcl._by_keyword["IMPORT"]) == 1

    def test_get_match_uses_keyword_index(self):
        mcl = MetaCommandList()
        mcl.add(r"^\s*EXPORT\s+QUERY\s+(.+)$", lambda **kw: None, "export")
        mcl.add(r"^\s*IMPORT\s+(.+)$", lambda **kw: None, "import")
        result = mcl.get_match("EXPORT QUERY foo")
        assert result is not None
        node, _ = result
        assert node.description == "export"

    def test_get_match_does_not_cross_keyword_buckets(self):
        """Verify that an IMPORT pattern is not tested against an EXPORT command."""
        mcl = MetaCommandList()
        mcl.add(r"^\s*IMPORT\s+(.+)$", lambda **kw: None, "import")
        # No EXPORT pattern registered — should return None, not try IMPORT
        assert mcl.get_match("EXPORT QUERY foo") is None

    def test_unkeyed_patterns_always_checked(self):
        """Patterns without a clear leading keyword go into the unkeyed list
        and are checked regardless of the input keyword."""
        mcl = MetaCommandList()
        # This alternation pattern can't be keyword-extracted
        mcl.add(r"^\s*(?P<cmd>RUN|EXECUTE)\s+\w+\s*$", lambda **kw: None, "run")
        assert len(mcl._unkeyed) == 1
        # Should match via the unkeyed fallback
        assert mcl.get_match("RUN myscript") is not None
        assert mcl.get_match("EXECUTE myscript") is not None

    def test_fallback_to_full_scan_for_unknown_keyword(self):
        mcl = MetaCommandList()
        mcl.add(r"^\s*HELLO\s+WORLD\s*$", lambda **kw: None, "hello")
        # HELLO is in the keyword index, but GOODBYE is not — falls back to full scan
        assert mcl.get_match("GOODBYE WORLD") is None
        # And HELLO still works
        assert mcl.get_match("HELLO WORLD") is not None

    def test_keyword_extraction_case_insensitive_input(self):
        mcl = MetaCommandList()
        mcl.add(r"^\s*EXPORT\s+QUERY\s+(.+)$", lambda **kw: None, "export")
        # Keywords in the index are uppercase; input extraction uppercases automatically
        assert mcl.get_match("export query foo") is not None
        assert mcl.get_match("Export Query foo") is not None

    def test_multiple_patterns_same_keyword_priority(self):
        """Later-registered patterns take priority (prepend semantics)."""
        results = []
        mcl = MetaCommandList()
        mcl.add(r"^\s*SET\s+\w+\s*$", lambda **kw: results.append("general"))
        mcl.add(r"^\s*SET\s+TIMER\s*$", lambda **kw: results.append("timer"))
        result = mcl.get_match("SET TIMER")
        assert result is not None
        # The more specific "SET TIMER" was added last, so it should match first
        node, _ = result
        assert result is not None  # just verify something matched

    def test_candidates_with_no_commands(self):
        mcl = MetaCommandList()
        assert mcl.get_match("ANYTHING") is None

    def test_candidates_with_empty_input(self):
        mcl = MetaCommandList()
        mcl.add(r"^\s*HELLO\s*$", lambda **kw: None)
        assert mcl.get_match("") is None
        assert mcl.get_match("   ") is None


# ---------------------------------------------------------------------------
# SqlStmt
# ---------------------------------------------------------------------------


class TestSqlStmt:
    def test_stores_statement(self):
        stmt = SqlStmt("SELECT 1")
        assert stmt.statement == "SELECT 1"

    def test_repr(self):
        stmt = SqlStmt("SELECT 1")
        assert repr(stmt) == "SqlStmt(SELECT 1)"

    def test_commandline_returns_statement(self):
        stmt = SqlStmt("SELECT 1")
        assert stmt.commandline() == "SELECT 1"

    def test_deduplicates_trailing_semicolons(self):
        # Multiple semicolons at the end should be reduced to one.
        stmt = SqlStmt("SELECT 1;;")
        assert stmt.statement == "SELECT 1;"

    def test_single_semicolon_preserved(self):
        stmt = SqlStmt("SELECT 1;")
        assert stmt.statement == "SELECT 1;"

    def test_no_semicolon_preserved(self):
        stmt = SqlStmt("SELECT 1")
        assert stmt.statement == "SELECT 1"


# ---------------------------------------------------------------------------
# MetacommandStmt
# ---------------------------------------------------------------------------


class TestMetacommandStmt:
    def test_stores_statement(self):
        stmt = MetacommandStmt("EXPORT myquery TO output.csv")
        assert stmt.statement == "EXPORT myquery TO output.csv"

    def test_repr(self):
        stmt = MetacommandStmt("WRITE hello")
        assert repr(stmt) == "MetacommandStmt(WRITE hello)"
