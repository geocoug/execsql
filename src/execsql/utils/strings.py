from __future__ import annotations

"""
String manipulation utilities for execsql.

Provides helpers used when processing column headers and quoted
identifiers:

- :func:`clean_word` / :func:`clean_words` — replace non-alphanumeric
  characters with underscores and add a leading underscore if the first
  character is a digit.
- :func:`trim_words` — strip leading/trailing whitespace from each word.
- :func:`fold_words` — convert to lower/upper case.
- :func:`dedup_words` — de-duplicate a list of words by appending
  numeric suffixes.
- :func:`is_doublequoted` / :func:`unquoted` — detect and strip SQL
  double-quote delimiters.
- :func:`get_subvarset` — resolve a variable-set name to the
  appropriate :class:`~execsql.script.SubVarSet` instance.
- :func:`encodings_match` — check whether two encoding names are
  equivalent.
"""

import re

__all__ = [
    "clean_word",
    "clean_words",
    "trim_word",
    "trim_words",
    "fold_word",
    "fold_words",
    "dedup_words",
    "is_doublequoted",
    "unquoted",
    "unquoted2",
    "encodings_match",
    "wo_quotes",
    "get_subvarset",
]


def clean_word(word: str) -> str:
    # Trim leading and trailing spaces and replaces all non-alphanumeric characters with an underscore.
    s1 = re.sub(r"\W+", "_", word.strip(), flags=re.I)
    # Maybe add leading underscore.
    if s1[0] in "0123456789":
        return "_" + s1
    return s1


def clean_words(wordlist: list[str]) -> list[str]:
    return [clean_word(w) for w in wordlist]


def trim_word(word: str, blr: str) -> str:
    # Trim leading and trailing spaces and underscores - both, left, or right
    if blr == "both":
        return word.strip("_ ")
    elif blr == "left":
        return word.lstrip("_ ")
    elif blr == "right":
        return word.rstrip("_ ")
    else:
        return word


def trim_words(wordlist: list[str], nblr: str) -> list[str]:
    return [trim_word(w, nblr) for w in wordlist]


def fold_word(word: str, foldspec: str) -> str:
    # foldspec should be 'no', 'lower', or 'upper'.
    if foldspec == "lower":
        return word.lower()
    elif foldspec == "upper":
        return word.upper()
    return word


def fold_words(wordlist: list[str], foldspec: str) -> list[str]:
    return [fold_word(w, foldspec) for w in wordlist]


def dedup_words(wordlist: list[str]) -> list[str]:
    # Adds an item number suffix to duplicated words.
    w2 = wordlist
    dup_ix = [ix for ix, w in enumerate(w2) if w.lower() in [wrd.lower() for wrd in w2[:ix]]]
    while len(dup_ix) > 0:
        w2 = [w + f"_{str(ix + 1)}" if ix in dup_ix else w for ix, w in enumerate(w2)]
        dup_ix = [ix for ix, w in enumerate(w2) if w.lower() in [wrd.lower() for wrd in w2[:ix]]]
    return w2


def is_doublequoted(s: str) -> bool:
    return len(s) > 1 and s[0] == '"' and s[-1] == '"'


def unquoted(phrase: str, quotechars: str = '"') -> str:
    # Removes all quote characters in the given string only if they are paired
    # at the beginning and end of the string.
    removed = True
    newphrase = phrase
    while removed:
        removed = False
        if phrase is not None and len(newphrase) > 1:
            for qchar in quotechars:
                if newphrase[0] == qchar and newphrase[-1] == qchar:
                    newphrase = newphrase.strip(qchar)
                    removed = True
    return newphrase


def unquoted2(phrase: str) -> str:
    return unquoted(phrase, "'\"")


def encodings_match(enc1: str, enc2: str) -> bool:
    # Compares two encoding labels and returns T/F depending on whether or not
    # they match.  This implements the alias matching rules from Unicode Technical
    # Standard #22 (http://www.unicode.org/reports/tr22/tr22-7.html#Charset_Alias_Matching)
    # and a subset of the encoding equivalences listed at
    # https://encoding.spec.whatwg.org/#names-and-labels.
    enc1 = enc1.strip().lower()
    enc2 = enc2.strip().lower()
    if enc1 == enc2:
        return True
    rx = re.compile(r"[^a-z0-9]")
    enc1 = re.sub(rx, "", enc1)
    enc2 = re.sub(rx, "", enc2)
    if enc1 == enc2:
        return True
    rx = re.compile(r"0+(?P<tz>[1-9][0-9]*)")
    enc1 = re.sub(rx, r"\g<tz>", enc1)
    enc2 = re.sub(rx, r"\g<tz>", enc2)
    if enc1 == enc2:
        return True
    equivalents = (
        ("cp1252", "win1252", "windows1252", "latin1", "cp819", "csisolatin1", "ibm819", "iso88591", "l1", "xcp1252"),
        ("latin2", "csisolatin2", "iso88592", "isoir101", "l2"),
        ("latin3", "csisolatin3", "iso88593", "isoir109", "l3"),
        ("latin4", "csisolatin4", "iso88594", "isoir110", "l4"),
        ("latin5", "iso88599"),
        ("latin6", "iso885910", "csisolatin6", "isoir157", "l6"),
        ("latin7", "iso885913"),
        ("latin8", "iso885914"),
        ("latin9", "iso885915", "csisolatin9", "l9"),
        ("latin10", "iso885916"),
        (
            "cyrillic",
            "csisolatincyrillic",
            "iso88595",
            "isoir144",
            "win866",
            "windows866",
            "cp866",
        ),
        (
            "arabic",
            "win1256",
            "asmo708",
            "iso88596",
            "csiso88596e",
            "csiso88596i",
            "csisolatinarabic",
            "ecma114",
            "isoir127",
        ),
        (
            "greek",
            "win1253",
            "ecma118",
            "elot928",
            "greek8",
            "iso88597",
            "isoir126",
            "suneugreek",
        ),
        (
            "hebrew",
            "win1255",
            "iso88598",
            "csiso88598e",
            "csisolatinhebrew",
            "iso88598e",
            "isoir138",
            "visual",
        ),
        ("logical", "csiso88598i"),
        ("cp1250", "win1250", "windows1250", "xcp1250"),
        ("cp1251", "win1251", "windows1251", "xcp1251"),
        ("windows874", "win874", "cp874", "dos874", "iso885911", "tis620"),
        ("mac", "macintosh", "csmacintosh", "xmacroman"),
        ("xmaccyrillic", "xmacukrainian"),
        ("koi8u", "koi8ru"),
        ("koi8r", "koi", "koi8", "cskoi8r"),
        (
            "euckr",
            "cseuckr",
            "csksc56011987",
            "isoir149",
            "korean",
            "ksc56011987",
            "ksc56011989",
            "ksc5601",
            "windows949",
        ),
        ("eucjp", "xeucjp", "cseucpkdfmtjapanese"),
        ("csiso2022jp", "iso2022jp"),
        ("csshiftjis", "ms932", "ms-kanji", "shiftjis", "sjis", "windows-31j", "xsjis"),
        ("big5", "big5hkscs", "cnbig5", "csbig5", "xxbig5"),
        (
            "chinese",
            "csgb2312",
            "csiso58gb231280",
            "gb2312",
            "gb231280",
            "gbk",
            "isoir58",
            "xgbk",
            "gb18030",
        ),
    )
    return any(enc1 in eq and enc2 in eq for eq in equivalents)


def wo_quotes(argstr: str) -> str:
    # Strip first and last quotes off an argument.
    argstr = argstr.strip()
    if (
        argstr[0] == '"'
        and argstr[-1] == '"'
        or argstr[0] == "'"
        and argstr[-1] == "'"
        or argstr[0] == "["
        and argstr[-1] == "]"
    ):
        return argstr[1:-1]
    return argstr


def get_subvarset(varname: str, metacommandline: str) -> tuple:
    # Supports the exec functions for the substitution metacommands that allow
    # substitution variables with a "+" prefix, to reference outer scope local
    # variables
    import execsql.state as _state
    from execsql.exceptions import ErrInfo

    subvarset = None
    # Outer scope variable
    if varname[0] == "+":
        varname = re.sub("^[+]", "~", varname)
        for cl in reversed(_state.commandliststack[0:-1]):
            if cl.localvars.sub_exists(varname):
                subvarset = cl.localvars
                break
        # Raise error if local variable not found anywhere down in commandliststack
        if not subvarset:
            raise ErrInfo(
                type="cmd",
                command_text=metacommandline,
                other_msg="Outer-scope referent variable ({}) has no matching local variable ({}).".format(
                    re.sub("^[~]", "+", varname),
                    varname,
                ),
            )
    # Global or local variable
    else:
        subvarset = _state.subvars if varname[0] != "~" else _state.commandliststack[-1].localvars
    return subvarset, varname
