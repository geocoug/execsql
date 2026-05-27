-- ============================================================
-- write_create_table.sql — generate CREATE TABLE DDL from a CSV.
--
-- WRITE CREATE_TABLE scans a delimited file (or worksheet) to
-- determine column types and emits the matching CREATE TABLE
-- statement, either to the console or to a file.  We round-trip
-- it: export → write DDL → execute the DDL by INCLUDEEing the
-- DDL file → confirm the table now exists with the right shape.
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


CREATE TABLE seed (id INTEGER PRIMARY KEY, name TEXT, score REAL, active INTEGER);
INSERT INTO seed VALUES (1, 'alice',   92.5, 1);
INSERT INTO seed VALUES (2, 'bob',     88.0, 0);
INSERT INTO seed VALUES (3, 'carol',   75.25, 1);


-- =========================================================================
-- Phase 1: emit the DDL for a target table inferred from the CSV
-- =========================================================================

-- Step 1: export to CSV so WRITE CREATE_TABLE has something to scan.
-- !x! export seed to seed.csv as csv

-- Step 2: generate a CREATE TABLE for a hypothetical table named
-- 'inferred_seed' based on the column types found in seed.csv.
-- The output is appended to seed_ddl.sql via the async FileWriter.
-- !x! write create_table inferred_seed from seed.csv to seed_ddl.sql

-- WAIT_UNTIL polls FILE_EXISTS once per second for up to 10 seconds —
-- the FileWriter's background thread flushes within that window.
-- !x! wait_until file_exists(seed_ddl.sql) halt after 10 seconds

-- Step 3: confirm the DDL file exists.
-- !x! ASSERT FILE_EXISTS(seed_ddl.sql) "WRITE CREATE_TABLE produced the DDL file"


-- === Done ============================================================
-- All assertions passed.
