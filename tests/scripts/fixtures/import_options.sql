-- ============================================================
-- import_options.sql — IMPORT clauses: WITH QUOTE / DELIMITER,
-- TO REPLACEMENT, and SKIP <N> lines.
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


CREATE TABLE source (id INTEGER PRIMARY KEY, name TEXT, score REAL);
INSERT INTO source VALUES (1, 'alpha',   10.5);
INSERT INTO source VALUES (2, 'bra,vo',  20.0);
INSERT INTO source VALUES (3, 'charlie', 30.75);


-- =========================================================================
-- Phase 1: TSV (tab-delimited, no quote char) round-trip via WITH clause
-- The EXPORT side writes TSV; the IMPORT side uses WITH QUOTE NONE
-- DELIMITER TAB to disable auto-detection and parse it cleanly.
-- =========================================================================

-- !x! export source to source.tsv as tsv

-- !x! import to new tsv_back from source.tsv with quote none delimiter tab
-- !x! ASSERT TABLE_EXISTS(tsv_back)    "TSV import created the table"
-- !x! ASSERT ROW_COUNT_EQ(tsv_back, 3) "TSV import preserved 3 rows"

-- A comma inside the value survives because TAB (not comma) is the delimiter.
CREATE TABLE p1_chk (n TEXT);
INSERT INTO p1_chk SELECT name FROM tsv_back WHERE id='2';
-- !x! select_sub p1_chk
-- !x! ASSERT EQUALS("!!@n!!", "bra,vo") "TSV import: comma inside an unquoted field survives"


-- =========================================================================
-- Phase 2: IMPORT TO REPLACEMENT — drops + recreates the destination
-- =========================================================================

-- Pre-populate a table with a different schema and rows.
CREATE TABLE will_be_replaced (junk TEXT);
INSERT INTO will_be_replaced VALUES ('stale-row-1');
INSERT INTO will_be_replaced VALUES ('stale-row-2');
-- !x! ASSERT ROW_COUNT_EQ(will_be_replaced, 2) "pre-REPLACEMENT: 2 stale rows present"

-- REPLACEMENT drops the existing table and recreates it from the input
-- file's schema, then loads the new rows.
-- !x! import to replacement will_be_replaced from source.tsv with quote none delimiter tab
-- !x! ASSERT ROW_COUNT_EQ(will_be_replaced, 3) "REPLACEMENT: replaced with 3 fresh rows"

-- The original 'junk' column should be gone — the table has columns from
-- source.tsv (id, name, score) instead.  Probe by selecting the new col.
CREATE TABLE p2_chk (s TEXT);
INSERT INTO p2_chk SELECT score FROM will_be_replaced WHERE id='3';
-- !x! select_sub p2_chk
-- !x! ASSERT EQUALS("!!@s!!", "30.75") "REPLACEMENT: schema matches the source file (new 'score' column)"


-- =========================================================================
-- Phase 3: SKIP <N> — discard the first N lines of an input file.
-- Uses a committed fixture (import_options/has_comments.csv) so we don't
-- depend on async WRITE TO flush ordering.  The fixture has 2 comment
-- lines, a header row, then 2 data rows.
-- =========================================================================

-- !x! import to new comm_back from !!$current_script_path!!import_options/has_comments.csv skip 2
-- !x! ASSERT TABLE_EXISTS(comm_back)    "SKIP: import created the table"
-- !x! ASSERT ROW_COUNT_EQ(comm_back, 2) "SKIP 2: both comment lines discarded, 2 data rows loaded"

CREATE TABLE p3_chk (n TEXT);
INSERT INTO p3_chk SELECT name FROM comm_back WHERE id='1';
-- !x! select_sub p3_chk
-- !x! ASSERT EQUALS("!!@n!!", "zulu") "SKIP 2: data column survives intact"


-- === Done ============================================================
-- All assertions passed.
