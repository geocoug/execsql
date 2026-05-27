-- ============================================================
-- xlsx_ods_roundtrip.sql — IMPORT/EXPORT round-trips for
-- Microsoft Excel (.xlsx) and OpenDocument (.ods) spreadsheets.
--
-- Requires the `openpyxl` (XLSX) and `odfpy` (ODS) packages,
-- both of which are part of the `[formats]` install extra.
-- If either is missing the EXPORT line below halts with a
-- fatal_error message; the test will report a clear failure.
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


CREATE TABLE source (id INTEGER PRIMARY KEY, name TEXT, score REAL);
INSERT INTO source VALUES (1, 'alpha',    10.5);
INSERT INTO source VALUES (2, 'bravo,o',  20.0);
INSERT INTO source VALUES (3, 'charlie',  30.75);


-- =========================================================================
-- Phase 1: XLSX round-trip — EXPORT, then IMPORT TO NEW with SHEET clause
-- =========================================================================

-- !x! export source to source.xlsx as xlsx
-- !x! ASSERT FILE_EXISTS(source.xlsx) "XLSX export created the file"

-- IMPORT requires the SHEET name. EXPORT AS XLSX names the sheet after
-- the source table.
-- !x! import to new xlsx_back from excel source.xlsx sheet source
-- !x! ASSERT ROW_COUNT_EQ(xlsx_back, 3) "XLSX import recovered 3 rows"

-- Spot-check a value that includes a comma (would be hazardous in CSV).
CREATE TABLE p1_chk (n TEXT);
INSERT INTO p1_chk SELECT name FROM xlsx_back WHERE id='2';
-- !x! select_sub p1_chk
-- !x! ASSERT EQUALS("!!@n!!", "bravo,o") "XLSX preserves comma-containing strings (typed cells, not CSV)"


-- =========================================================================
-- Phase 2: ODS round-trip — same pattern with OpenDocument
-- =========================================================================

-- !x! export source to source.ods as ods
-- !x! ASSERT FILE_EXISTS(source.ods) "ODS export created the file"

-- ODS IMPORT also wants the SHEET clause.
-- !x! import to new ods_back from source.ods sheet source
-- !x! ASSERT ROW_COUNT_EQ(ods_back, 3) "ODS import recovered 3 rows"


-- === Done ============================================================
-- All assertions passed.
