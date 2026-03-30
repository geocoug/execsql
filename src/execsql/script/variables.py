from __future__ import annotations

"""Variable containers for execsql script execution.

Classes:
- :class:`CounterVars` — named auto-incrementing integer counters.
- :class:`SubVarSet` — global ``!!$VAR!!`` substitution-variable store.
- :class:`LocalSubVarSet` — per-script ``~``-prefixed local variable overlay.
- :class:`ScriptArgSubVarSet` — per-script ``#``-prefixed argument overlay.
"""

import os
import re
from typing import Any

from execsql.exceptions import ErrInfo


# ---------------------------------------------------------------------------
# CounterVars
# ---------------------------------------------------------------------------


class CounterVars:
    """Named auto-incrementing integer counters referenced as ``!!$COUNTER_N!!``."""

    # A dictionary of dynamically created named counter variables.
    _COUNTER_RX = re.compile(r"!!\$(COUNTER_\d+)!!", re.I)

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}

    def _ctrid(self, ctr_no: int) -> str:
        return f"counter_{ctr_no}"

    def set_counter(self, ctr_no: int, ctr_val: int) -> None:
        self.counters[self._ctrid(ctr_no)] = ctr_val

    def remove_counter(self, ctr_no: int) -> None:
        ctr_id = self._ctrid(ctr_no)
        if ctr_id in self.counters:
            del self.counters[ctr_id]

    def remove_all_counters(self) -> None:
        self.counters = {}

    def substitute(self, command_str: str) -> tuple:
        # Substitutes any counter variable references with the counter value and
        # returns the modified command string and a flag indicating replacements.
        m = self._COUNTER_RX.search(command_str, re.I)
        if m:
            ctr_id = m.group(1).lower()
            if ctr_id not in self.counters:
                self.counters[ctr_id] = 0
            new_count = self.counters[ctr_id] + 1
            self.counters[ctr_id] = new_count
            return command_str.replace("!!$" + m.group(1) + "!!", str(new_count)), True
        return command_str, False

    def substitute_all(self, any_text: str) -> tuple:
        subbed = True
        any_subbed = False
        while subbed:
            any_text, subbed = self.substitute(any_text)
            if subbed:
                any_subbed = True
        return any_text, any_subbed


# ---------------------------------------------------------------------------
# SubVarSet / LocalSubVarSet / ScriptArgSubVarSet
# ---------------------------------------------------------------------------


class SubVarSet:
    """Pool of ``!!$VAR!!``-style substitution variables.

    Variable names are stored in lowercase.  Supports ``$``, ``&``, and ``@``
    prefixes by default.  Use :meth:`add_substitution` / :meth:`remove_substitution`
    to manage entries, and :meth:`substitute_all` to expand a string.
    """

    # A pool of substitution variables.  Each variable consists of a name and
    # a (string) value.  All variable names are stored as lowercase text.
    # Internally uses a dict for O(1) lookups; the ``substitutions`` property
    # exposes the data as a list of ``(name, value)`` tuples for backward
    # compatibility with external code.
    def __init__(self) -> None:
        self._subs_dict: dict[str, Any] = {}
        self._compiled_patterns: dict[str, tuple] = {}
        self.prefix_list: list[str] = ["$", "&", "@"]
        # Don't construct/compile on init because deepcopy() can't handle compiled regexes.
        self.var_rx = None

    @property
    def substitutions(self) -> list[tuple]:
        """Backward-compatible view of substitutions as a list of (name, value) tuples."""
        return list(self._subs_dict.items())

    @substitutions.setter
    def substitutions(self, value: Any) -> None:
        """Accept a list of (name, value) tuples or a dict and populate the internal dict."""
        if isinstance(value, dict):
            self._subs_dict = dict(value)
        else:
            self._subs_dict = dict(value)
        self._rebuild_all_patterns()

    def _compile_patterns_for(self, varname: str) -> tuple:
        """Compile and return the three regex patterns (plain, single-quoted, double-quoted) for *varname*."""
        match_escaped = "\\" + varname if varname[0] == "$" else varname
        pat = re.compile(f"!!{match_escaped}!!", re.I)
        patq = re.compile(f"!'!{match_escaped}!'!", re.I)
        patdq = re.compile(f'!"!{match_escaped}!"!', re.I)
        return (pat, patq, patdq)

    def _rebuild_all_patterns(self) -> None:
        """Rebuild compiled patterns for every variable currently stored."""
        self._compiled_patterns = {}
        for varname in self._subs_dict:
            self._compiled_patterns[varname] = self._compile_patterns_for(varname)

    def compile_var_rx(self) -> None:
        """Compile the variable-name validation regex from the current prefix list."""
        self.var_rx_str = r"^[" + "".join(self.prefix_list) + r"]?\w+$"
        self.var_rx = re.compile(self.var_rx_str, re.I)

    def var_name_ok(self, varname: str) -> bool:
        if self.var_rx is None:
            self.compile_var_rx()
        return self.var_rx.match(varname) is not None

    def check_var_name(self, varname: str) -> None:
        if not self.var_name_ok(varname.lower()):
            raise ErrInfo("error", other_msg=f"Invalid variable name ({varname}) in this context.")

    def remove_substitution(self, template_str: str) -> None:
        """Remove the variable named *template_str* from the substitution pool."""
        self.check_var_name(template_str)
        old_sub = template_str.lower()
        self._subs_dict.pop(old_sub, None)
        self._compiled_patterns.pop(old_sub, None)

    def add_substitution(self, varname: str, repl_str: Any) -> None:
        """Add or overwrite a substitution variable, compiling its match patterns."""
        self.check_var_name(varname)
        varname = varname.lower()
        self._subs_dict[varname] = repl_str
        self._compiled_patterns[varname] = self._compile_patterns_for(varname)

    def append_substitution(self, varname: str, repl_str: str) -> None:
        self.check_var_name(varname)
        varname = varname.lower()
        if varname in self._subs_dict:
            self.add_substitution(varname, f"{self._subs_dict[varname]}\n{repl_str}")
        else:
            self.add_substitution(varname, repl_str)

    def varvalue(self, varname: str) -> str | None:
        """Return the value of *varname*, or ``None`` if it is not defined."""
        self.check_var_name(varname)
        return self._subs_dict.get(varname.lower())

    def increment_by(self, varname: str, numeric_increment: Any) -> None:
        self.check_var_name(varname)
        varvalue = self.varvalue(varname)
        if varvalue is None:
            varvalue = "0"
            self.add_substitution(varname, varvalue)
        # Import as_numeric lazily to avoid circular dependency
        from execsql.utils.numeric import as_numeric

        numvalue = as_numeric(varvalue)
        numinc = as_numeric(numeric_increment)
        if numvalue is None or numinc is None:
            newval = f"{varvalue}+{numeric_increment}"
        else:
            newval = str(numvalue + numinc)
        self.add_substitution(varname, newval)

    def sub_exists(self, template_str: str) -> bool:
        """Return True if the variable named *template_str* is defined."""
        self.check_var_name(template_str)
        return template_str.lower() in self._subs_dict

    def merge(self, other_subvars: SubVarSet | None) -> SubVarSet:
        """Return a new SubVarSet with this object's variables merged with other_subvars."""
        if other_subvars is not None:
            newsubs = SubVarSet()
            newsubs._subs_dict = dict(self._subs_dict)
            newsubs._compiled_patterns = dict(self._compiled_patterns)
            newsubs.prefix_list = list(set(self.prefix_list + other_subvars.prefix_list))
            newsubs.compile_var_rx()
            for varname, value in other_subvars._subs_dict.items():
                newsubs.add_substitution(varname, value)
            return newsubs
        return self

    # Combined regex matching any variable token in one pass.
    # Group 1: quote marker — empty for plain !!var!!, ' for !'!var!'!, " for !"!var!"!
    # Group 2: variable name (with optional prefix character)
    _TOKEN_RX = re.compile(
        r"!(?P<q>['\"]?)!(?P<varname>[$&@~#]?\w+)!(?P=q)!",
        re.I,
    )

    def substitute(self, command_str: str) -> tuple:
        """Replace the first matching variable token in *command_str*.

        Uses a single combined regex to find any ``!!var!!``, ``!'!var!'!``, or
        ``!"!var!"!`` token in one pass, then looks up the variable name in the
        dict.  This is O(1) per call instead of O(V) where V is the number of
        defined variables.

        Returns ``(modified_string, True)`` if a substitution was made, or
        ``(original_string, False)`` if no variable pattern matched.
        """
        if not isinstance(command_str, str):
            return command_str, False
        m = self._TOKEN_RX.search(command_str)
        while m:
            varname = m.group("varname").lower()
            if varname in self._subs_dict:
                sub = self._subs_dict[varname]
                if sub is None:
                    sub = ""
                sub = str(sub)
                if os.name != "posix":
                    sub = sub.replace("\\", "\\\\")
                quote = m.group("q")
                if quote == "'":
                    sub = sub.replace("'", "''")
                elif quote == '"':
                    sub = '"' + sub + '"'
                return command_str[: m.start()] + sub + command_str[m.end() :], True
            # Token found but variable not defined — skip it and keep searching.
            m = self._TOKEN_RX.search(command_str, m.end())
        return command_str, False

    def substitute_all(self, any_text: str) -> tuple:
        """Repeatedly apply :meth:`substitute` until no more substitutions remain.

        Returns ``(fully_expanded_string, any_substitution_made)``.
        """
        subbed = True
        any_subbed = False
        while subbed:
            any_text, subbed = self.substitute(any_text)
            if subbed:
                any_subbed = True
        return any_text, any_subbed


class LocalSubVarSet(SubVarSet):
    """Substitution-variable pool restricted to ``~``-prefixed local variables."""

    # A pool of local substitution variables.
    # Only '~' is allowed as a prefix and MUST be present.
    def __init__(self) -> None:
        SubVarSet.__init__(self)
        self.prefix_list = ["~"]

    def compile_var_rx(self) -> None:
        # Prefix is required, not optional.
        self.var_rx_str = r"^[" + "".join(self.prefix_list) + r"]\w+$"
        self.var_rx = re.compile(self.var_rx_str, re.I)


class ScriptArgSubVarSet(SubVarSet):
    """Substitution-variable pool restricted to ``#``-prefixed script arguments."""

    # A pool of script argument names.
    # Only '#' is allowed as a prefix and MUST be present.
    def __init__(self) -> None:
        SubVarSet.__init__(self)
        self.prefix_list = ["#"]

    def compile_var_rx(self) -> None:
        # Prefix is required, not optional.
        self.var_rx_str = r"^[" + "".join(self.prefix_list) + r"]\w+$"
        self.var_rx = re.compile(self.var_rx_str, re.I)
