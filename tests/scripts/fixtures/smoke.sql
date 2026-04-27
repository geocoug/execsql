-- ============================================================
-- smoke.sql — Happy-path workflow test for execsql2
--
-- Exercises the most common metacommand combinations in a
-- realistic pipeline: variable setup, table creation, data
-- population, conditional branching, CSV export/import, and
-- cross-verification of imported data.
--
-- Run manually:
--   python -m execsql tests/scripts/fixtures/smoke.sql test.db -t l -n
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


-- === Phase 1: Variable setup and table creation ================

-- !x! sub project_name smoke_test
-- !x! sub version 1
-- !x! sub row_target 5

CREATE TABLE source (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL,
    value REAL
);

INSERT INTO source (id, name, value) VALUES (1, 'alpha',   10.5);
INSERT INTO source (id, name, value) VALUES (2, 'bravo',   20.0);
INSERT INTO source (id, name, value) VALUES (3, 'charlie', 30.75);
INSERT INTO source (id, name, value) VALUES (4, 'delta',   40.0);
INSERT INTO source (id, name, value) VALUES (5, 'echo',    50.25);

-- !x! ASSERT TABLE_EXISTS(source) "source table must exist"
-- !x! ASSERT HASROWS(source) "source table must have rows"
-- !x! ASSERT ROW_COUNT_EQ(source, 5) "source must have exactly 5 rows"


-- === Phase 2: SELECT_SUB to capture computed values =============

CREATE TABLE summary (
    total_rows INTEGER,
    max_id     INTEGER,
    sum_value  REAL
);

INSERT INTO summary
    SELECT COUNT(*), MAX(id), SUM(value)
    FROM source;

-- !x! select_sub summary

-- Captured variables: !!@total_rows!!, !!@max_id!!, !!@sum_value!!

CREATE TABLE sub_check (total_rows TEXT, max_id TEXT);
INSERT INTO sub_check VALUES ('!!@total_rows!!', '!!@max_id!!');

-- !x! ASSERT EQUALS(!!@total_rows!!, 5) "SELECT_SUB total_rows should be 5"
-- !x! ASSERT EQUALS(!!@max_id!!, 5) "SELECT_SUB max_id should be 5"


-- === Phase 3: SUB_ADD and SUB_APPEND ============================

-- !x! sub counter 0
-- !x! sub_add counter 5
-- !x! ASSERT EQUALS(!!counter!!, 5) "SUB_ADD: 0 + 5 = 5"

-- !x! sub_add counter -2
-- !x! ASSERT EQUALS(!!counter!!, 3) "SUB_ADD: 5 + (-2) = 3"

-- !x! sub path_parts base
-- !x! sub_append path_parts segment1
-- !x! ASSERT SUB_DEFINED(path_parts) "path_parts should be defined"


-- === Phase 4: Conditional branching based on data ===============

-- !x! if (is_gt(!!@total_rows!!, 3))
-- !x! sub status large_dataset
-- !x! else
-- !x! sub status small_dataset
-- !x! endif

CREATE TABLE branch_result (status TEXT);
INSERT INTO branch_result VALUES ('!!status!!');

-- !x! ASSERT EQUALS(!!status!!, large_dataset) "5 rows > 3, so status should be large_dataset"


-- Nested IF/ELSEIF/ELSE
-- !x! sub tier gold

-- !x! if (equals(!!tier!!, platinum))
-- !x! sub discount 30
-- !x! elseif (equals(!!tier!!, gold))
-- !x! sub discount 20
-- !x! else
-- !x! sub discount 0
-- !x! endif

-- !x! ASSERT EQUALS(!!discount!!, 20) "gold tier should get 20% discount"


-- === Phase 5: Export to CSV, then re-import =====================

-- !x! export source to exported_source.csv as csv
-- !x! ASSERT FILE_EXISTS(exported_source.csv) "CSV export file must exist"

-- !x! import to new imported_source from exported_source.csv
-- !x! ASSERT TABLE_EXISTS(imported_source) "imported table must exist"
-- !x! ASSERT ROW_COUNT_EQ(imported_source, 5) "imported table must have 5 rows"


-- === Phase 6: Cross-verify imported data matches original =======

CREATE TABLE match_check (match_count INTEGER);

INSERT INTO match_check
    SELECT COUNT(*)
    FROM source s
    JOIN imported_source i ON CAST(s.id AS TEXT) = i.id
    WHERE s.name = i.name;

-- !x! select_sub match_check

-- All 5 rows should have matching id + name across source and import
-- !x! ASSERT EQUALS(!!@match_count!!, 5) "all 5 rows should match after CSV round-trip"


-- === Phase 7: WRITE to console ==================================

-- WRITE to file uses async FileWriter, so FILE_EXISTS is race-prone.
-- Instead, verify WRITE to console works with variable substitution.
-- !x! write "Smoke test: project=!!project_name!!, version=!!version!!"


-- === Done =======================================================
-- If we reach here, all assertions passed.
