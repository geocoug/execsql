"""B17/F013 regression: ``substitute_vars`` aborts when expanded
output exceeds :data:`_MAX_SUBSTITUTION_BYTES` (default 10 MB).

The pre-existing depth cap (``_MAX_SUBSTITUTION_DEPTH = 100``) only
stops cyclic references — a variable referencing itself or another in
a loop. It does NOT stop exponential expansion: a single variable
``a = "!!b!! !!b!!"`` doubles output per iteration without ever
looping. Track rendered length and raise after a configurable byte
ceiling.
"""

from __future__ import annotations

import pytest

from execsql.exceptions import ErrInfo
from execsql.script.engine import _MAX_SUBSTITUTION_BYTES, substitute_vars
from execsql.script.variables import CounterVars, SubVarSet


@pytest.fixture(autouse=True)
def seed_state():
    """substitute_vars needs _state.subvars + _state.counters; the
    autouse minimal_conf fixture only sets _state.conf."""
    import execsql.state as _state

    saved_subvars = _state.subvars
    saved_counters = _state.counters
    _state.subvars = SubVarSet()
    _state.counters = CounterVars()
    # Default: no override on the byte cap.
    if not hasattr(_state.conf, "max_substitution_bytes"):
        _state.conf.max_substitution_bytes = None
    yield
    _state.subvars = saved_subvars
    _state.counters = saved_counters


class TestExpansionBomb:
    def test_legitimate_expansion_under_cap_succeeds(self):
        """A single substitution of a normal-sized value succeeds."""
        sv = SubVarSet()
        sv.add_substitution("name", "Alice")
        out = substitute_vars("Hello !!name!!", localvars=sv)
        assert out == "Hello Alice"

    def test_accumulating_expansion_rejected(self):
        """A handful of moderate substitutions that together exceed
        the cap are rejected before they accumulate further. Each
        substitute_all iteration replaces one token at a time, so
        the inner depth cap (100) lets ~100 substitutions through;
        the byte cap is the second line of defence."""
        import execsql.state as _state

        sv = SubVarSet()
        # Cap is 10 KB; each !!chunk!! is 2 KB; 10 references → 20 KB.
        _state.conf.max_substitution_bytes = 10_000
        sv.add_substitution("chunk", "X" * 2000)
        with pytest.raises(ErrInfo, match="expansion exceeded"):
            substitute_vars("!!chunk!! " * 10, localvars=sv)

    def test_oversized_substitution_at_default_cap(self):
        """A single substitution that ALREADY exceeds the cap is
        rejected on the first iteration."""
        import execsql.state as _state

        sv = SubVarSet()
        _state.conf.max_substitution_bytes = 1024
        huge = "X" * 2048
        sv.add_substitution("huge", huge)
        with pytest.raises(ErrInfo, match="expansion exceeded"):
            substitute_vars("[!!huge!!]", localvars=sv)

    def test_default_cap_is_10_MB(self):
        assert _MAX_SUBSTITUTION_BYTES == 10 * 1024 * 1024

    def test_conf_override_respected(self):
        """conf.max_substitution_bytes overrides the engine default."""
        import execsql.state as _state

        sv = SubVarSet()
        sv.add_substitution("v", "X" * 100)
        # Cap below the value length → reject.
        _state.conf.max_substitution_bytes = 50
        with pytest.raises(ErrInfo, match="expansion exceeded"):
            substitute_vars("!!v!!", localvars=sv)
        # Cap above the value length → succeed.
        _state.conf.max_substitution_bytes = 200
        assert substitute_vars("!!v!!", localvars=sv) == "X" * 100

    def test_cycle_still_caught_with_byte_cap_disabled(self):
        """Even with a generous byte cap, a cyclic reference is caught
        — either by the inner ``SubVarSet.substitute_all`` cycle
        detector (``RuntimeError``) or the outer ``substitute_vars``
        depth cap (``ErrInfo``), depending on which fires first."""
        import execsql.state as _state

        sv = SubVarSet()
        _state.conf.max_substitution_bytes = 10_000_000_000
        sv.add_substitution("a", "!!b!!")
        sv.add_substitution("b", "!!a!!")
        with pytest.raises((RuntimeError, ErrInfo), match="cycle"):
            substitute_vars("[!!a!!]", localvars=sv)

    def test_input_already_over_cap_still_substitutes_first_pass(self):
        """If the INPUT (before substitution) already exceeds the cap,
        the first substitution iteration still completes; the cap is
        checked AFTER the iteration, so legitimate large literals
        without substitution pass through silently to the caller.

        This matches the docstring: the cap targets expansion, not
        pre-existing literal size.
        """
        import execsql.state as _state

        sv = SubVarSet()
        _state.conf.max_substitution_bytes = 1024
        # 2 KB literal, no substitutions
        big_literal = "X" * 2048
        # With no !!var!! tokens, substitute_all returns (input, False)
        # on the first iteration, the while-loop exits, and we never
        # check the cap. So this should pass.
        out = substitute_vars(big_literal, localvars=sv)
        assert out == big_literal
