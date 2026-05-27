-- ============================================================
-- config_runtime.sql — Runtime CONFIG toggles that change
-- the behavior of subsequent EXPORT / IMPORT operations.
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


CREATE TABLE seed (id INTEGER PRIMARY KEY, label TEXT);
INSERT INTO seed VALUES (1, 'one'), (2, 'two'), (3, 'three');


-- =========================================================================
-- Phase 1: CONFIG MAKE_EXPORT_DIRS — auto-create parent dirs on EXPORT
-- Default is "No": exporting to a path whose parent dir does not exist
-- fails.  Setting it to "Yes" causes EXPORT to mkdir -p along the way.
-- =========================================================================

-- (a) Default behaviour — nested-dir export fails.
-- !x! metacommand_error_halt off
-- !x! export seed to nested/deeper/out.csv as csv
-- !x! ASSERT METACOMMAND_ERROR() "default MAKE_EXPORT_DIRS=No: nested-dir EXPORT rejected"
-- !x! metacommand_error_halt on

-- (b) After turning the config on, the same export succeeds.
-- !x! config make_export_dirs yes
-- !x! export seed to nested/deeper/out.csv as csv
-- !x! ASSERT FILE_EXISTS(nested/deeper/out.csv) "MAKE_EXPORT_DIRS=Yes: nested dirs auto-created"

-- (c) Revert to default for subsequent phases.
-- !x! config make_export_dirs no


-- =========================================================================
-- Phase 2: IMPORT_ONLY_COMMON_COLUMNS — tolerate extra CSV columns
-- The CSV has columns (id, label, extra). The destination table has
-- only (id, label).  Default: error. Toggle on: skip the extra column.
-- =========================================================================

-- Build the wide CSV via EXPORT.
CREATE TABLE wide (id INTEGER PRIMARY KEY, label TEXT, extra TEXT);
INSERT INTO wide VALUES (10, 'a', 'unused-1'), (20, 'b', 'unused-2');
-- !x! export wide to wide.csv as csv

-- Destination table has only id + label.
CREATE TABLE narrow (id INTEGER PRIMARY KEY, label TEXT);

-- (a) Default — extra column makes IMPORT fail.
-- !x! metacommand_error_halt off
-- !x! import to narrow from wide.csv
-- !x! ASSERT METACOMMAND_ERROR() "default IMPORT_ONLY_COMMON_COLUMNS=No: wide CSV rejected"
-- !x! metacommand_error_halt on

-- (b) Toggle on — extra column silently ignored.
-- !x! import_only_common_columns yes
-- !x! import to narrow from wide.csv

-- !x! ASSERT ROW_COUNT_EQ(narrow, 2) "IMPORT_ONLY_COMMON_COLUMNS=Yes: 2 rows imported, 'extra' col dropped"

-- Revert (each test runs in its own subprocess anyway, but be explicit).
-- !x! import_only_common_columns no


-- === Done ============================================================
-- All assertions passed.
