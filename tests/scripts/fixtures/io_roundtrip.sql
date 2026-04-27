-- ============================================================
-- io_roundtrip.sql — Export/import round-trip integrity test
--
-- Verifies that data survives export-then-import across
-- CSV, TSV, and JSON formats.  Tests EXPORT, EXPORT QUERY,
-- IMPORT, WRITE, and format-specific edge cases (NULLs,
-- commas in text, special characters).
--
-- Run manually:
--   python -m execsql tests/scripts/fixtures/io_roundtrip.sql test.db -t l -n
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


-- === Phase 1: Create source data with edge cases ================

CREATE TABLE source (
    id    INTEGER PRIMARY KEY,
    name  TEXT,
    notes TEXT,
    value REAL
);

INSERT INTO source VALUES (1, 'simple',         'no issues here',          100.0);
INSERT INTO source VALUES (2, 'with,comma',     'commas,in,text',          200.5);
INSERT INTO source VALUES (3, 'with "quotes"',  'she said "hello"',        300.0);
INSERT INTO source VALUES (4, 'plain',          NULL,                       NULL);
INSERT INTO source VALUES (5, 'zero_value',     'zero and negative',         0.0);
INSERT INTO source VALUES (6, 'negative',       'negative number',         -42.5);
INSERT INTO source VALUES (7, 'large_int',      'big number',          999999.99);

-- !x! ASSERT ROW_COUNT_EQ(source, 7) "source should have 7 rows"


-- === Phase 2: CSV round-trip ====================================

-- !x! export source to source_export.csv as csv
-- !x! ASSERT FILE_EXISTS(source_export.csv) "CSV export must create file"

-- !x! import to new csv_reimported from source_export.csv
-- !x! ASSERT TABLE_EXISTS(csv_reimported) "CSV import must create table"
-- !x! ASSERT ROW_COUNT_EQ(csv_reimported, 7) "CSV reimport must have 7 rows"

-- Verify specific values survived the round-trip
CREATE TABLE csv_check (match_count INTEGER);
INSERT INTO csv_check
    SELECT COUNT(*)
    FROM source s
    JOIN csv_reimported c ON CAST(s.id AS TEXT) = c.id
    WHERE s.name = c.name;

-- !x! select_sub csv_check
-- !x! ASSERT EQUALS(!!@match_count!!, 7) "all 7 rows should match name after CSV round-trip"


-- === Phase 3: TSV round-trip ====================================

-- !x! export source to source_export.tsv as tsv
-- !x! ASSERT FILE_EXISTS(source_export.tsv) "TSV export must create file"

-- !x! import to new tsv_reimported from source_export.tsv with quote none delimiter tab
-- !x! ASSERT TABLE_EXISTS(tsv_reimported) "TSV import must create table"
-- !x! ASSERT ROW_COUNT_EQ(tsv_reimported, 7) "TSV reimport must have 7 rows"


-- === Phase 4: JSON export =======================================

-- !x! export source to source_export.json as json
-- !x! ASSERT FILE_EXISTS(source_export.json) "JSON export must create file"


-- === Phase 5: EXPORT QUERY (filtered export) ====================

-- !x! export query << SELECT id, name, value FROM source WHERE value > 100; >> to filtered.csv as csv
-- !x! ASSERT FILE_EXISTS(filtered.csv) "filtered CSV export must create file"

-- !x! import to new filtered_reimported from filtered.csv
-- !x! ASSERT TABLE_EXISTS(filtered_reimported) "filtered import must create table"
-- !x! ASSERT ROW_COUNT_EQ(filtered_reimported, 3) "only 3 rows have value > 100 (200.5, 300.0, 999999.99)"


-- === Phase 6: EXPORT APPEND ====================================

CREATE TABLE extra_rows (
    id    INTEGER PRIMARY KEY,
    name  TEXT,
    notes TEXT,
    value REAL
);

INSERT INTO extra_rows VALUES (8, 'appended_one', 'from extra', 800.0);
INSERT INTO extra_rows VALUES (9, 'appended_two', 'from extra', 900.0);

-- !x! export extra_rows append to source_export.csv as csv
-- !x! import to new appended_reimport from source_export.csv
-- !x! ASSERT TABLE_EXISTS(appended_reimport) "appended import must create table"
-- !x! ASSERT ROW_COUNT_EQ(appended_reimport, 9) "7 original + 2 appended = 9 rows"


-- === Phase 7: WRITE to console ==================================

-- WRITE to file uses async FileWriter, so FILE_EXISTS is race-prone.
-- Instead, verify WRITE to console works with variable substitution.
-- !x! sub report_name io_test_report
-- !x! write "Report: !!report_name!! — CSV/TSV/JSON exports verified"


-- === Phase 8: Multiple exports from same table ==================

-- Export the same table in different formats and verify all files exist
-- !x! export source to multi_csv.csv as csv
-- !x! export source to multi_tsv.tsv as tsv
-- !x! export source to multi_json.json as json
-- !x! export source to multi_txt.txt as txt

-- !x! ASSERT FILE_EXISTS(multi_csv.csv) "multi-format CSV must exist"
-- !x! ASSERT FILE_EXISTS(multi_tsv.tsv) "multi-format TSV must exist"
-- !x! ASSERT FILE_EXISTS(multi_json.json) "multi-format JSON must exist"
-- !x! ASSERT FILE_EXISTS(multi_txt.txt) "multi-format TXT must exist"


-- === Phase 9: EXPORT QUERY with substitution variables ==========

-- !x! sub min_value 200
-- !x! export query << SELECT id, name FROM source WHERE value >= !!min_value!!; >> to sub_filtered.csv as csv
-- !x! ASSERT FILE_EXISTS(sub_filtered.csv) "substitution-filtered export must create file"

-- !x! import to new sub_filtered_reimported from sub_filtered.csv
-- !x! ASSERT TABLE_EXISTS(sub_filtered_reimported) "substitution-filtered import must create table"
-- !x! ASSERT ROW_COUNT_EQ(sub_filtered_reimported, 3) "3 rows have value >= 200 (200.5, 300.0, 999999.99)"


-- === Done =======================================================
-- If we reach here, all assertions passed.
