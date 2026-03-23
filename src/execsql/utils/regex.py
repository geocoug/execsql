from __future__ import annotations

"""
Regular expression building utilities for execsql.

Provides helpers used when constructing the metacommand and conditional
dispatch regexes at module load time:

- :func:`ins_rxs` — inserts a list of regex fragments between two
  surrounding fragments, returning all combinations.
- Other pattern-composition helpers used by the metacommand registration
  code in :mod:`execsql.metacommands.__init__`.
"""

import os
import re
from typing import List, Optional, Tuple


def ins_rxs(rx_list: tuple, fragment1: object, fragment2: object) -> tuple:
    # Returns a tuple of all strings consisting of elements of the 'rx_list' tuple
    # inserted between 'fragment1' and 'fragment2'.  The fragments may themselves
    # be tuples.
    if type(fragment1) != tuple:
        fragment1 = (fragment1,)
    if fragment2 is None:
        fragment2 = ("",)
    if type(fragment2) != tuple:
        fragment2 = (fragment2,)
    rv = []
    for te in rx_list:
        for f1 in fragment1:
            for f2 in fragment2:
                rv.append(f1 + te + f2)
    return tuple(rv)


def ins_quoted_rx(fragment1: object, fragment2: object, rx: str) -> tuple:
    return ins_rxs((rx, r'"%s"' % rx), fragment1, fragment2)


def ins_schema_rxs(fragment1: object, fragment2: object, suffix: Optional[str] = None) -> tuple:
    schema_exprs = (
        r'"(?P<schema>[A-Za-z0-9_\- ]+)"',
        r"(?P<schema>[A-Za-z0-9_\-]+)",
        r"\[(?P<schema>[A-Za-z0-9_\- ]+)\]",
    )
    if suffix:
        schema_exprs = tuple([s.replace("schema", "schema" + suffix) for s in schema_exprs])
    return ins_rxs(schema_exprs, fragment1, fragment2)


def ins_table_rxs(fragment1: object, fragment2: object, suffix: Optional[str] = None) -> tuple:
    tbl_exprs = (
        r'(?:"(?P<schema>[A-Za-z0-9_\- ]+)"\.)?"(?P<table>[A-Za-z0-9_\-\# ]+)"',
        r"(?:(?P<schema>[A-Za-z0-9_\-]+)\.)?(?P<table>[A-Za-z0-9_\-\#]+)",
        r'(?:"(?P<schema>[A-Za-z0-9_\- ]+)"\.)?(?P<table>[A-Za-z0-9_\-\#]+)',
        r'(?:(?P<schema>[A-Za-z0-9_\-]+)\.)?"(?P<table>[A-Za-z0-9_\-\# ]+)"',
        r"(?:\[(?P<schema>[A-Za-z0-9_\- ]+)\]\.)?\[(?P<table>[A-Za-z0-9_\-\# ]+)\]",
        r"(?:(?P<schema>[A-Za-z0-9_\-]+)\.)?(?P<table>[A-Za-z0-9_\-\#]+)",
        r"(?:\[(?P<schema>[A-Za-z0-9_\- ]+)\]\.)?(?P<table>[A-Za-z0-9_\-\#]+)",
        r"(?:(?P<schema>[A-Za-z0-9_\-]+)\.)?\[(?P<table>[A-Za-z0-9_\-\# ]+)\]",
    )
    if suffix:
        tbl_exprs = tuple(
            [s.replace("schema", "schema" + suffix).replace("table", "table" + suffix) for s in tbl_exprs],
        )
    return ins_rxs(tbl_exprs, fragment1, fragment2)


def ins_table_list_rxs(fragment1: object, fragment2: object) -> tuple:
    tbl_exprs = (
        r'(?:(?P<tables>(?:"[A-Za-z0-9_\- ]+"\.)?"[A-Za-z0-9_\-\# ]+"(?:\s*,\s*(?:"[A-Za-z0-9_\- ]+"\.)?"[A-Za-z0-9_\-\# ]+")*))',
        r"(?:(?P<tables>(?:[A-Za-z0-9_\-]+\.)?[A-Za-z0-9_\-\#]+(?:\s*,\s*(?:[A-Za-z0-9_\-]+\.)?[A-Za-z0-9_\-\#]+)*))",
    )
    return ins_rxs(tbl_exprs, fragment1, fragment2)


def ins_fn_rxs(fragment1: object, fragment2: object, symbolicname: str = "filename") -> tuple:
    if os.name == "posix":
        fns = (
            r"(?P<%s>[\w\.\-\\\/\'~`!@#$^&()+={}\[\]:;,]*[\w\.\-\\\/\'~`!@#$^&(+={}\[\]:;,])" % symbolicname,
            r'"(?P<%s>[\w\s\.\-\\\/\'~`!@#$^&()+={}\[\]:;,]+)"' % symbolicname,
        )
    else:
        fns = (
            r"(?P<%s>([A-Z]\:)?[\w+\,()!@#$^&\+=;\'{}\[\]~`\.\-\\\/]*[\w+\,(!@#$^&\+=;\'{}\[\]~`\.\-\\\/])"
            % symbolicname,
            r'"(?P<%s>([A-Z]\:)?[\w+\,()!@#$^&\+=;\'{}\[\]~`\s\.\-\\\/]+)"' % symbolicname,
        )
    return ins_rxs(fns, fragment1, fragment2)
