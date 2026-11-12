"""Differential checks against the pre-optimization nested substitution scan."""

from __future__ import annotations

from itertools import permutations
import random

import pytest

from execsql.script.variables import (
    SubVarSet,
    _after_escape_string_prefix,
    _sql_string_literal,
)


class LegacySubVarSet(SubVarSet):
    # Frozen from 2.40.0: preserve definition order, quote priority and errors.
    def _substitute_nested(self, command_str: str) -> tuple:
        """Scan for any defined variable as a substring — handles nested tokens.

        Uses case-insensitive string search instead of per-variable regex
        compilation to avoid O(N) ``re.compile`` calls on every invocation.
        """
        # Every token below starts with one of these, so text without them
        # can't match; skip the scan over every defined variable.
        if "!!" not in command_str and "!'!" not in command_str and '!"!' not in command_str:
            return command_str, False
        cmd_lower = command_str.lower()

        def _check_nul(name: str, value: str) -> None:
            """B07a/F002: raise when *value* (about to be interpolated)
            contains a NUL byte. Called only after a token match so an
            unrelated variable's NUL value never blocks substitution of
            a different variable."""
            if "\x00" in value:
                raise ValueError(
                    f"Substitution variable {name!r} contains a NUL byte; refusing to interpolate.",
                )

        for varname, sub in self._subs_dict.items():
            if sub is None:
                sub = ""
            sub = str(sub)
            # Standard token: !!varname!!
            token = f"!!{varname}!!"
            idx = cmd_lower.find(token)
            if idx != -1:
                _check_nul(varname, sub)
                return command_str[:idx] + sub + command_str[idx + len(token) :], True
            # Single-quote-wrapped token: !'!varname!'! — a string literal.
            tokenq = f"!'!{varname}!'!"
            idxq = cmd_lower.find(tokenq)
            if idxq != -1:
                _check_nul(varname, sub)
                wrapped = _sql_string_literal(sub, escape_string=_after_escape_string_prefix(command_str, idxq))
                return (
                    command_str[:idxq] + wrapped + command_str[idxq + len(tokenq) :],
                    True,
                )
            # Double-quote-wrapped token: !"!varname!"! — double embedded ``"``.
            tokendq = f'!"!{varname}!"!'
            idxdq = cmd_lower.find(tokendq)
            if idxdq != -1:
                _check_nul(varname, sub)
                return (
                    command_str[:idxdq] + '"' + sub.replace('"', '""') + '"' + command_str[idxdq + len(tokendq) :],
                    True,
                )
        return command_str, False


def _outcome(variables, text, *, nested=False, expand=False):
    """Record every replacement, including the step and message of a failure."""
    trace = []
    try:
        if expand:
            return ("return", variables.substitute_all(text))
        for _ in range(100):
            text, changed = variables._substitute_nested(text) if nested else variables.substitute(text)
            trace.append((text, changed))
            if not changed:
                break
    except Exception as error:
        return ("error", type(error), str(error), trace)
    return ("trace", trace)


def _compare(entries, text, *, nested=False, expand=False):
    actual, legacy = SubVarSet(), LegacySubVarSet()
    actual.substitutions = entries
    legacy.substitutions = entries
    assert _outcome(actual, text, nested=nested, expand=expand) == _outcome(
        legacy,
        text,
        nested=nested,
        expand=expand,
    ), (entries, text)


@pytest.mark.parametrize("order", list(permutations(("left", "right", "outer"))))
@pytest.mark.parametrize("nested", (False, True))
def test_definition_order_and_quote_priority(order, nested):
    values = {"left": "!!right!!", "right": "X", "outer": "done"}
    entries = [(name, values[name]) for name in order]
    for text in (
        "!!N_!!right!!_CHECKS!! !!N_!!left!!_CHECKS!!",
        "!'!left!'! !!left!! !\"!left!\"!",
        "!!left!! !!right!!",
        "!!outer!! !!N_!!left!!_CHECKS!!",
    ):
        _compare(entries, text, nested=nested)


@pytest.mark.parametrize("nested", (False, True))
@pytest.mark.parametrize("quote", ("", "'", '"'))
@pytest.mark.parametrize("name", ("a", "$x", "@x", "&x", "~x", "#x", "É", "İ", "a.b", "a b", "a!b", ""))
def test_token_forms_and_compatibility_names(nested, quote, name):
    marker = "!" + quote + "!"
    for value in (None, 0, 1.25, "O'Brien\\data", "line\nbreak", "\x00", "!!a!!"):
        _compare([(name.lower(), value)], "prefix " + marker + name + marker, nested=nested)


def test_fallback_definition_order_differs_from_text_order():
    # The public single-step API must still expand the later text token
    # first when its variable was defined first.
    entries = [("b", "X"), ("a", "!!b!!"), ("n_x", "done")]
    _compare(entries, "!!N_!!a!!!! !!N_!!b!!!!", expand=True)
    variables = SubVarSet()
    variables.substitutions = [("b", "X"), ("a", "Y")]
    assert variables.substitute("!!N_!!a!!!! !!N_!!b!!!!") == ("!!N_!!a!!!! !!N_X!!", True)


@pytest.mark.parametrize("nested", (False, True))
def test_generated_differential_traces(nested):
    rng = random.Random(20261112)
    names = ["a", "b", "$x", "@c", "é", "i\u0307", "a.b", "a!b", "a\nb", ""]
    values = [None, 0, -2, 1.25, "O'Brien", "\\path", "", "\x00", "!!b!!", "!!a!!", "!!a!!!!a!!"]
    for _ in range(600):
        rng.shuffle(names)
        entries = [(name, rng.choice(values)) for name in names[: rng.randrange(1, len(names) + 1)]]
        pieces = []
        for _ in range(rng.randrange(1, 7)):
            name = rng.choice(names + ["MISSING", "İ"])
            marker = rng.choice(("!!", "!'!", '!"!'))
            token = marker + name + marker
            pieces.append(rng.choice((token, "!!N_" + token + "_CHECKS!!", "E" + token, "text")))
        text = rng.choice((" ", "", "\n", "!")).join(pieces)
        _compare(entries, text, nested=nested)
        if not nested:
            _compare(entries, text, expand=True)


def test_mutations_and_lazy_materialization_keep_the_original_order():
    actual, legacy = SubVarSet(), LegacySubVarSet()
    for variables in (actual, legacy):
        variables.add_substitution("a", "A")
        variables.add_substitution("b", "B")
        variables.register_lazy("$lazy", lambda: "L")
    texts = ["!!N_!!b!!!! !!N_!!a!!!!", "!!N_!!$lazy!!!!", "!!$lazy!!"]
    for action in ("initial", "overwrite", "remove_reinsert", "clear_lazy", "merge", "setter"):
        for variables in (actual, legacy):
            if action == "overwrite":
                variables.add_substitution("a", "new")
            elif action == "remove_reinsert":
                variables.remove_substitution("a")
                variables.add_substitution("a", "last")
            elif action == "clear_lazy":
                variables.clear_lazy_cache()
            elif action == "merge":
                other = SubVarSet()
                other.add_substitution("b", "merged")
                merged = variables.merge(other)
                variables.substitutions = merged.substitutions
            elif action == "setter":
                variables.substitutions = list(reversed(variables.substitutions))
        for text in texts:
            assert _outcome(actual, text) == _outcome(legacy, text), action


def test_unreferenced_values_are_converted_in_the_original_order():
    class BadValue:
        def __str__(self):
            raise ValueError("conversion failed")

    _compare([("unreferenced", BadValue()), ("a", "A")], "!!N_!!a!!!!")


def test_compatibility_setter_keeps_non_string_keys():
    _compare([(123, "value")], "!!N_!!123!!!!", nested=True)
