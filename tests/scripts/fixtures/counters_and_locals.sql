-- ============================================================
-- counters_and_locals.sql — Counter vars, local vars, script args,
-- and a handful of system-var corner cases ($RANDOM / $UUID).
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


-- =========================================================================
-- Phase 1: $COUNTER_x — auto-incrementing on each reference
-- =========================================================================

-- A counter starts at 1 on first reference.
CREATE TABLE c1_tbl (val INTEGER);
INSERT INTO c1_tbl VALUES (!!$counter_1!!);
INSERT INTO c1_tbl VALUES (!!$counter_1!!);
INSERT INTO c1_tbl VALUES (!!$counter_1!!);

-- Three references → 1, 2, 3.
CREATE TABLE c1_chk (vals TEXT);
INSERT INTO c1_chk SELECT GROUP_CONCAT(val, ',') FROM (SELECT val FROM c1_tbl ORDER BY rowid);
-- !x! select_sub c1_chk
-- !x! ASSERT EQUALS("!!@vals!!", "1,2,3") "counter_1 increments 1,2,3 across 3 references"


-- =========================================================================
-- Phase 2: Multiple references in the same statement get the same value
-- =========================================================================

CREATE TABLE c2_tbl (a INTEGER, b INTEGER);
-- Both !!$counter_2!! references in this INSERT should yield the SAME value.
INSERT INTO c2_tbl VALUES (!!$counter_2!!, !!$counter_2!!);
-- The next reference (separate statement) increments.
INSERT INTO c2_tbl VALUES (!!$counter_2!!, !!$counter_2!!);

CREATE TABLE c2_chk (got TEXT);
INSERT INTO c2_chk
  SELECT GROUP_CONCAT(a || '=' || b, ',')
  FROM (SELECT a, b FROM c2_tbl ORDER BY rowid);
-- !x! select_sub c2_chk
-- !x! ASSERT EQUALS("!!@got!!", "1=1,2=2") "counter_2 same within one statement, increments across statements"


-- =========================================================================
-- Phase 3: SET COUNTER — preload, then the next reference returns N+1
-- =========================================================================

-- !x! set counter 3 to 99
CREATE TABLE c3_tbl (val INTEGER);
INSERT INTO c3_tbl VALUES (!!$counter_3!!);
INSERT INTO c3_tbl VALUES (!!$counter_3!!);

CREATE TABLE c3_chk (vals TEXT);
INSERT INTO c3_chk SELECT GROUP_CONCAT(val, ',') FROM (SELECT val FROM c3_tbl ORDER BY rowid);
-- !x! select_sub c3_chk
-- !x! ASSERT EQUALS("!!@vals!!", "100,101") "SET COUNTER 3 TO 99 → next refs return 100, 101"


-- =========================================================================
-- Phase 4: RESET COUNTER — back to 1 on the next reference
-- =========================================================================

-- counter_1 is already at 4 from Phase 1 (3 refs took it past 3).
-- !x! reset counter 1
CREATE TABLE c4_tbl (val INTEGER);
INSERT INTO c4_tbl VALUES (!!$counter_1!!);
INSERT INTO c4_tbl VALUES (!!$counter_1!!);

CREATE TABLE c4_chk (vals TEXT);
INSERT INTO c4_chk SELECT GROUP_CONCAT(val, ',') FROM (SELECT val FROM c4_tbl ORDER BY rowid);
-- !x! select_sub c4_chk
-- !x! ASSERT EQUALS("!!@vals!!", "1,2") "RESET COUNTER 1 → restart at 1"


-- =========================================================================
-- Phase 5: Local variables (~prefix) — only live inside a SCRIPT scope
-- =========================================================================

-- !x! begin script with_local
-- !x! sub ~local_only inside-script-only
INSERT INTO _local_audit VALUES ('inside:!!~local_only!!');
-- !x! end script

CREATE TABLE _local_audit (note TEXT);
-- !x! execute script with_local

-- Outside the script, !!~local_only!! is undefined.
-- !x! if (sub_defined(~local_only))
INSERT INTO _local_audit VALUES ('leaked');
-- !x! else
INSERT INTO _local_audit VALUES ('not-leaked');
-- !x! endif

CREATE TABLE p5_chk (got TEXT);
INSERT INTO p5_chk SELECT GROUP_CONCAT(note, '|') FROM (SELECT note FROM _local_audit ORDER BY rowid);
-- !x! select_sub p5_chk
-- !x! ASSERT EQUALS("!!@got!!", "inside:inside-script-only|not-leaked") "local ~var visible inside SCRIPT, undefined outside"


-- =========================================================================
-- Phase 6: $RANDOM — same value within one statement, distinct across
-- =========================================================================

CREATE TABLE r6_tbl (a TEXT, b TEXT);
INSERT INTO r6_tbl VALUES ('!!$random!!', '!!$random!!');
INSERT INTO r6_tbl VALUES ('!!$random!!', '!!$random!!');

-- Same-statement consistency: both columns of each row must agree.
CREATE TABLE r6_same (n INTEGER);
INSERT INTO r6_same SELECT COUNT(*) FROM r6_tbl WHERE a = b;
-- !x! select_sub r6_same
-- !x! ASSERT EQUALS("!!@n!!", "2") "$RANDOM: both refs in one statement match (rows 1 and 2)"

-- Cross-statement distinctness: row 1's value differs from row 2's.
CREATE TABLE r6_diff (n INTEGER);
INSERT INTO r6_diff SELECT COUNT(DISTINCT a) FROM r6_tbl;
-- !x! select_sub r6_diff
-- !x! ASSERT EQUALS("!!@n!!", "2") "$RANDOM: distinct values across statements"


-- =========================================================================
-- Phase 7: $UUID — same value within one statement, 32 hex chars
-- =========================================================================

CREATE TABLE u7_tbl (a TEXT, b TEXT);
INSERT INTO u7_tbl VALUES ('!!$uuid!!', '!!$uuid!!');

-- Same-statement consistency.
CREATE TABLE u7_same (a TEXT, b TEXT);
INSERT INTO u7_same SELECT a, b FROM u7_tbl;
-- !x! select_sub u7_same
-- !x! ASSERT EQUALS("!!@a!!", "!!@b!!") "$UUID: both refs in one statement are identical"

-- Length is 36 chars (canonical hyphenated 8-4-4-4-12 form, e.g.
-- "550e8400-e29b-41d4-a716-446655440000").
CREATE TABLE u7_len (n INTEGER);
INSERT INTO u7_len SELECT LENGTH(a) FROM u7_tbl;
-- !x! select_sub u7_len
-- !x! ASSERT EQUALS("!!@n!!", "36") "$UUID: canonical hyphenated 36-char form"


-- === Done ============================================================
-- All assertions passed.
