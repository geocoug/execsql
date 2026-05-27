-- ============================================================
-- template_export.sql — EXPORT WITH TEMPLATE (string.Template form).
--
-- The default template processor replaces $colname placeholders
-- with values from each row of the exported table, concatenating
-- the rendered text into a single output file.  Uses a committed
-- template at template_export/greeting.tmpl.
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT, score INTEGER);
INSERT INTO people VALUES (1, 'alice', 92);
INSERT INTO people VALUES (2, 'bob',   88);
INSERT INTO people VALUES (3, 'carol', 75);


-- =========================================================================
-- Phase 1: Render the template once per row, write to greetings.txt
-- =========================================================================

-- !x! export people to greetings.txt with template !!$current_script_path!!template_export/greeting.tmpl

-- !x! ASSERT FILE_EXISTS(greetings.txt) "template export produced the output file"


-- === Done ============================================================
-- All assertions passed.
