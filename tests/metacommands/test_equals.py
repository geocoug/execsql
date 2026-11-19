"""Preserve forgiving EQUAL results while skipping conversions for matching text."""

import itertools
import unicodedata

import pytest

import execsql
from execsql.metacommands import conditions


def _before_fast_path(first, second):
    """Frozen conversion algorithm from 2.41.0, before normalized-text short circuiting."""
    first = unicodedata.normalize("NFC", first).lower().strip('"')
    second = unicodedata.normalize("NFC", second).lower().strip('"')
    for convert in (
        int,
        float,
        conditions.DT_Timestamp().from_data,
        conditions.DT_TimestampTZ().from_data,
        conditions.DT_Date().from_data,
        conditions.DT_Boolean().from_data,
    ):
        try:
            if convert(first) == convert(second):
                return True
        except Exception:
            continue
    return first == second


@pytest.mark.parametrize("boolean_int,boolean_words", itertools.product((False, True), repeat=2))
def test_matches_previous_conversion_algorithm(minimal_conf, boolean_int, boolean_words):
    minimal_conf.boolean_int = boolean_int
    minimal_conf.boolean_words = boolean_words
    values = (
        "",
        '""',
        " ",
        "alpha",
        "ALPHA",
        '"Alpha"',
        "beta",
        "ÉCOLE",
        "e\u0301cole",
        "ß",
        "SS",
        "0",
        "1",
        "01",
        "2",
        "1.0",
        "1.25",
        "1.250",
        "-0",
        "nan",
        "NaN",
        "inf",
        "true",
        "t",
        "yes",
        "false",
        "f",
        "no",
        "2020-01-02",
        "Jan 2, 2020",
        "2020-01-03",
        "2020-01-02 03:00:00",
        "2020-01-02 04:00:00",
        "2020-01-02 03:00:00+01:00",
        "2020-01-02 02:00:00+00:00",
        "invalid date",
    )
    for first, second in itertools.product(values, repeat=2):
        assert conditions.xf_equals(string1=first, string2=second) is _before_fast_path(first, second), (first, second)


@pytest.mark.parametrize(
    "first,second,expected",
    [
        ("ÉCOLE", "e\u0301cole", True),
        ('"Alpha"', "ALPHA", True),
        ("", '""', True),
        ("NaN", "nan", True),
        ("01", "1", True),
        ("1.25", "1.250", True),
        ("true", "t", True),
        ("true", "1", True),
        ("2020-01-02", "Jan 2, 2020", True),
        ("2020-01-02 03:00:00+01:00", "2020-01-02 02:00:00+00:00", True),
        ("alpha", "beta", False),
        ("1.25", "1.5", False),
        ("2020-01-02 03:00:00", "2020-01-02 04:00:00", False),
        ("false", "true", False),
        (" ", "", False),
        ("ß", "SS", False),
    ],
)
def test_expected_results(first, second, expected):
    assert conditions.xf_equals(string1=first, string2=second) is expected


@pytest.mark.parametrize("first,second", [(None, ""), ("", None), (1, "1"), ("1", 1)])
def test_non_string_inputs_still_raise(first, second):
    with pytest.raises(TypeError):
        conditions.xf_equals(string1=first, string2=second)


def test_script_comparisons():
    result = execsql.run(
        dsn="sqlite:///:memory:",
        sql="""-- !x! ASSERT EQUAL("ÉCOLE", "e\u0301cole")
-- !x! ASSERT EQUAL("NaN", "nan")
-- !x! ASSERT EQUAL("01", "1")
-- !x! ASSERT EQUAL("true", "1")
-- !x! ASSERT NOT EQUAL("alpha", "beta")
""",
    )
    assert result.success, result.errors
