-- ============================================================
-- subvars_advanced.sql — Less-trafficked substitution operations.
--
-- Covers SUB_EMPTY, RM_SUB, SUBDATA, SUB_LOCAL, SUB_TEMPFILE,
-- $-prefixed system vars, and the !{var}! deferred-substitution
-- form (evaluated on every iteration, not once at parse time).
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


-- =========================================================================
-- Phase 1: SUB_EMPTY — defines a variable with an empty string value
-- =========================================================================

-- !x! sub_empty maybe_value
-- !x! ASSERT SUB_DEFINED(maybe_value) "SUB_EMPTY defines the variable"

CREATE TABLE p1_chk (v TEXT);
INSERT INTO p1_chk VALUES ('[!!maybe_value!!]');
-- !x! select_sub p1_chk
-- !x! ASSERT EQUALS("!!@v!!", "[]") "SUB_EMPTY value is the empty string"


-- =========================================================================
-- Phase 2: RM_SUB — undefine a substitution variable
-- =========================================================================

-- !x! sub temp_var something
-- !x! ASSERT SUB_DEFINED(temp_var) "temp_var defined before RM_SUB"

-- !x! rm_sub temp_var
-- !x! ASSERT NOT SUB_DEFINED(temp_var) "temp_var undefined after RM_SUB"


-- =========================================================================
-- Phase 3: SUBDATA — bind a sub var to "first column of first row"
-- =========================================================================

CREATE TABLE meta_kv (val TEXT);
INSERT INTO meta_kv VALUES ('hello-world');

-- !x! subdata first_val meta_kv
-- !x! ASSERT SUB_DEFINED(first_val) "SUBDATA defined the variable"

CREATE TABLE p3_chk (v TEXT);
INSERT INTO p3_chk VALUES ('!!first_val!!');
-- !x! select_sub p3_chk
-- !x! ASSERT EQUALS("!!@v!!", "hello-world") "SUBDATA pulled 'hello-world' from first row"

-- Per docs: empty source = variable undefined.
DELETE FROM meta_kv;
-- !x! subdata empty_val meta_kv
-- !x! ASSERT NOT SUB_DEFINED(empty_val) "SUBDATA on empty table leaves variable undefined"


-- =========================================================================
-- Phase 4: SUB_LOCAL — define a local variable without the ~ prefix
-- =========================================================================

-- !x! begin script with_sub_local
-- !x! sub_local lvar_a inside-script
INSERT INTO _ls_audit VALUES ('script:!!~lvar_a!!');
-- !x! end script

CREATE TABLE _ls_audit (note TEXT);
-- !x! execute script with_sub_local

-- !x! if (sub_defined(~lvar_a))
INSERT INTO _ls_audit VALUES ('leaked');
-- !x! else
INSERT INTO _ls_audit VALUES ('not-leaked');
-- !x! endif

CREATE TABLE p4_chk (got TEXT);
INSERT INTO p4_chk SELECT GROUP_CONCAT(note, '|') FROM (SELECT note FROM _ls_audit ORDER BY rowid);
-- !x! select_sub p4_chk
-- !x! ASSERT EQUALS("!!@got!!", "script:inside-script|not-leaked") "SUB_LOCAL is script-scoped (same as ~prefix)"


-- =========================================================================
-- Phase 5: SUB_TEMPFILE — assign a unique temp-file path
-- =========================================================================

-- !x! sub_tempfile tf1
-- !x! sub_tempfile tf2
-- !x! ASSERT SUB_DEFINED(tf1) "SUB_TEMPFILE defined tf1"
-- !x! ASSERT SUB_DEFINED(tf2) "SUB_TEMPFILE defined tf2"

-- The two temp paths must be different (each call returns a unique name).
CREATE TABLE tf_chk (a TEXT, b TEXT, distinct_n INTEGER);
INSERT INTO tf_chk VALUES ('!!tf1!!', '!!tf2!!', 0);
UPDATE tf_chk SET distinct_n = CASE WHEN a = b THEN 0 ELSE 1 END;
-- !x! select_sub tf_chk
-- !x! ASSERT EQUALS("!!@distinct_n!!", "1") "SUB_TEMPFILE returns distinct paths per call"


-- =========================================================================
-- Phase 6: $CURRENT_ALIAS — initial DB alias is "initial"
-- =========================================================================

CREATE TABLE alias_chk (v TEXT);
INSERT INTO alias_chk VALUES ('!!$current_alias!!');
-- !x! select_sub alias_chk
-- !x! ASSERT EQUALS("!!@v!!", "initial") "$CURRENT_ALIAS is 'initial' before any CONNECT"


-- =========================================================================
-- Phase 7: !{var}! deferred substitution — evaluated per-iteration
-- =========================================================================

-- A LOOP WHILE that uses !!i!! (frozen at parse time) would never exit.
-- Using !{i}! re-substitutes each iteration so the condition tracks the
-- mutating value. This is the same pattern used in control_flow.sql but
-- exercised here as the explicit feature under test.

-- !x! sub i 0
-- !x! loop while (not is_gte(!{i}!, 4))
-- !x! sub_add i 1
-- !x! end loop
-- !x! ASSERT EQUALS("!!i!!", "4") "!{var}! deferred substitution: loop exits after 4 increments"


-- === Done ============================================================
-- All assertions passed.
