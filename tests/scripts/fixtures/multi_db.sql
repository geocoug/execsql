-- ============================================================
-- multi_db.sql — Multiple connections, USE, COPY across DBs.
--
-- Connects to a second SQLite file alongside the harness-provided
-- initial DB, switches between them with USE, copies a table
-- across with COPY (NEW) and COPY (REPLACEMENT), copies the
-- result of a query with COPY QUERY, then disconnects.
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


-- =========================================================================
-- Phase 1: Open a second SQLite database alongside the initial one
-- =========================================================================

-- !x! connect to sqlite(file=second.db, new) as second

-- USE applies subsequent SQL statements to the named alias. We're still
-- writing to "initial" here.
CREATE TABLE source_tbl (id INTEGER PRIMARY KEY, name TEXT, score REAL);
INSERT INTO source_tbl VALUES (1, 'alice',   92.5);
INSERT INTO source_tbl VALUES (2, 'bob',     88.0);
INSERT INTO source_tbl VALUES (3, 'carol',   75.25);

-- !x! ASSERT TABLE_EXISTS(source_tbl) "source_tbl exists in initial DB"
-- !x! ASSERT ROW_COUNT_EQ(source_tbl, 3) "source_tbl seeded with 3 rows"


-- =========================================================================
-- Phase 2: COPY NEW — auto-create the destination table in 'second'
-- =========================================================================

-- !x! copy source_tbl from initial to new dest_tbl in second

-- Switch to the second DB and assert the copy landed.
-- !x! use second
-- !x! ASSERT TABLE_EXISTS(dest_tbl) "COPY NEW created dest_tbl in second DB"
-- !x! ASSERT ROW_COUNT_EQ(dest_tbl, 3) "COPY NEW transferred all 3 rows"

-- Spot-check a row.
CREATE TABLE p2_chk (name TEXT, score TEXT);
INSERT INTO p2_chk SELECT name, score FROM dest_tbl WHERE id=2;
-- !x! select_sub p2_chk
-- !x! ASSERT EQUALS("!!@name!!", "bob")   "COPY preserved string column"
-- !x! ASSERT EQUALS("!!@score!!", "88.0") "COPY preserved numeric column"


-- =========================================================================
-- Phase 3: USE switches the SQL target — confirm initial still has data
-- =========================================================================

-- Switch back to the initial DB and verify source is untouched.
-- !x! use initial
-- !x! ASSERT ROW_COUNT_EQ(source_tbl, 3) "initial DB still has source_tbl (unchanged)"

-- Confirm dest_tbl is NOT in the initial DB (it lives in second).
-- !x! ASSERT NOT TABLE_EXISTS(dest_tbl) "dest_tbl only exists in second DB"


-- =========================================================================
-- Phase 4: COPY REPLACEMENT — drops + recreates an existing destination
-- =========================================================================

-- Add a row to the source, then REPLACE the destination.
INSERT INTO source_tbl VALUES (4, 'dave', 100.0);
-- !x! copy source_tbl from initial to replacement dest_tbl in second

-- !x! use second
-- !x! ASSERT ROW_COUNT_EQ(dest_tbl, 4) "COPY REPLACEMENT now has 4 rows"


-- =========================================================================
-- Phase 5: COPY QUERY — push a filtered subset from initial to second
-- =========================================================================

-- !x! copy query <<SELECT id, name FROM source_tbl WHERE score >= 90;>> from initial to new high_scores in second

-- !x! use second
-- !x! ASSERT TABLE_EXISTS(high_scores)     "COPY QUERY created the high_scores table"
-- !x! ASSERT ROW_COUNT_EQ(high_scores, 2)  "COPY QUERY filtered to score >= 90 (alice + dave)"


-- =========================================================================
-- Phase 6: DISCONNECT and confirm the alias is gone
-- =========================================================================

-- Switch off the second DB before disconnecting (can't disconnect the
-- currently-in-use one without USE'ing somewhere else first).
-- !x! use initial
-- !x! disconnect second

-- Trying to USE a disconnected alias must fail.
-- !x! metacommand_error_halt off
-- !x! use second
-- !x! ASSERT METACOMMAND_ERROR() "USE on disconnected alias is rejected"
-- !x! metacommand_error_halt on


-- === Done ============================================================
-- All assertions passed.
