-- ============================================================
-- predicates.sql — Exhaustive coverage of the IF/ASSERT predicates
-- that aren't otherwise exercised: IDENTICAL, IS_NULL, IS_TRUE,
-- IS_FALSE, IS_ZERO, plus the SUB_DEFINED variants for ~local
-- and @data variables.
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


-- =========================================================================
-- Phase 1: IDENTICAL vs EQUAL — case-sensitive vs case-insensitive
-- EQUAL normalises and is permissive; IDENTICAL is strict.
-- =========================================================================

-- !x! ASSERT EQUAL("hello", "HELLO")     "EQUAL: case-insensitive match"
-- !x! ASSERT NOT IDENTICAL("hello", "HELLO") "IDENTICAL: case-sensitive non-match"

-- !x! ASSERT EQUAL("1", "1.0")           "EQUAL: numeric-tolerant ('1' = '1.0')"
-- !x! ASSERT NOT IDENTICAL("1", "1.0")   "IDENTICAL: string strict ('1' != '1.0')"

-- !x! ASSERT IDENTICAL("abc", "abc")     "IDENTICAL: exact match passes"


-- =========================================================================
-- Phase 2: IS_NULL — true for None-ish substitution values
-- =========================================================================

-- !x! sub_empty empty_var
-- !x! ASSERT IS_NULL("!!empty_var!!")    "IS_NULL: SUB_EMPTY value treated as null"
-- !x! ASSERT NOT IS_NULL("anything")     "IS_NULL: non-empty literal is not null"


-- =========================================================================
-- Phase 3: IS_TRUE / IS_FALSE — boolean literals
-- =========================================================================

-- Per docs, IS_TRUE accepts: Yes, Y, True, T, 1 (case-insensitive).
-- IS_FALSE accepts: No, N, False, F, 0.  Notably "on" / "off" are NOT
-- recognized (despite being common boolean words elsewhere in the
-- metacommand surface).
-- !x! ASSERT IS_TRUE("yes")     "IS_TRUE: 'yes'"
-- !x! ASSERT IS_TRUE("Y")       "IS_TRUE: 'Y' (single char)"
-- !x! ASSERT IS_TRUE("true")    "IS_TRUE: 'true'"
-- !x! ASSERT IS_TRUE("T")       "IS_TRUE: 'T' (single char)"
-- !x! ASSERT IS_TRUE("1")       "IS_TRUE: '1'"
-- !x! ASSERT NOT IS_TRUE("no")  "IS_TRUE: 'no' is not truthy"
-- !x! ASSERT NOT IS_TRUE("0")   "IS_TRUE: '0' is not truthy"
-- !x! ASSERT NOT IS_TRUE("anything-else") "IS_TRUE: arbitrary string is not truthy"

-- !x! ASSERT IS_FALSE("no")     "IS_FALSE: 'no'"
-- !x! ASSERT IS_FALSE("N")      "IS_FALSE: 'N' (single char)"
-- !x! ASSERT IS_FALSE("false")  "IS_FALSE: 'false'"
-- !x! ASSERT IS_FALSE("F")      "IS_FALSE: 'F' (single char)"
-- !x! ASSERT IS_FALSE("0")      "IS_FALSE: '0'"
-- !x! ASSERT NOT IS_FALSE("yes") "IS_FALSE: 'yes' is not falsy"
-- !x! ASSERT NOT IS_FALSE("anything-else") "IS_FALSE: arbitrary string is not falsy"


-- =========================================================================
-- Phase 4: IS_ZERO — numeric zero in various forms
-- =========================================================================

-- IS_ZERO requires an UNQUOTED numeric literal — quotes are not stripped
-- before the float() conversion, so IS_ZERO("0") fails with "not numeric".
-- !x! ASSERT IS_ZERO(0)        "IS_ZERO: integer 0"
-- !x! ASSERT IS_ZERO(0.0)      "IS_ZERO: float 0.0"
-- !x! ASSERT IS_ZERO(0.00000)  "IS_ZERO: padded float 0"
-- !x! ASSERT NOT IS_ZERO(0.1)  "IS_ZERO: 0.1 is non-zero"
-- !x! ASSERT NOT IS_ZERO(1)    "IS_ZERO: 1 is non-zero"
-- !x! ASSERT NOT IS_ZERO(-1)   "IS_ZERO: -1 is non-zero"


-- =========================================================================
-- Phase 5: SUB_DEFINED variants — global, ~local, @data prefixes
-- =========================================================================

-- (a) Global var
-- !x! sub g_var anything
-- !x! ASSERT SUB_DEFINED(g_var)     "SUB_DEFINED: global var present"
-- !x! ASSERT NOT SUB_DEFINED(g_var_missing) "SUB_DEFINED: missing global"

-- (b) Local ~var (defined inside SCRIPT)
-- !x! begin script defines_local
-- !x! sub ~loc_inside set-inside-script
-- !x! end script
-- !x! execute script defines_local
-- Local variables vanish when the SCRIPT body exits.
-- !x! ASSERT NOT SUB_DEFINED(~loc_inside) "SUB_DEFINED(~var): undefined after SCRIPT exits"

-- (c) Data @var (from SELECT_SUB)
CREATE TABLE _tmp (n TEXT);
INSERT INTO _tmp VALUES ('hello');
-- !x! select_sub _tmp
-- !x! ASSERT SUB_DEFINED(@n) "SUB_DEFINED(@col): set by SELECT_SUB"


-- === Done ============================================================
-- All assertions passed.
