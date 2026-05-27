-- ============================================================
-- includes.sql — INCLUDE another script file.
--
-- The include (`includes/helper.sql`) defines two substitution
-- variables and inserts a row into a table the parent created.
-- Asserts that:
--   1. SUB definitions in the include become visible
--   2. The include shares table scope with the includer
--   3. $CURRENT_SCRIPT_NAME inside the include reflects the
--      include filename, not the parent's
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


CREATE TABLE inc_audit (label TEXT, source TEXT);
INSERT INTO inc_audit VALUES ('parent-row-before-include', '!!$current_script_name!!');

-- Pull in the helper.  The path is anchored to this script's directory
-- so the test works regardless of cwd.
-- !x! include !!$current_script_path!!includes/helper.sql

-- Add another row after the include returns.
INSERT INTO inc_audit VALUES ('parent-row-after-include', '!!$current_script_name!!');

-- !x! ASSERT ROW_COUNT_EQ(inc_audit, 3) "parent + include + parent inserts visible"


-- =========================================================================
-- Variables defined inside the include are accessible after the INCLUDE
-- returns (substitution vars are global by default).
-- =========================================================================

-- !x! ASSERT SUB_DEFINED(helper_var)         "helper_var is defined after INCLUDE"
-- !x! ASSERT SUB_DEFINED(helper_script_name) "helper_script_name is defined after INCLUDE"

CREATE TABLE hv_chk (v TEXT);
INSERT INTO hv_chk VALUES ('!!helper_var!!');
-- !x! select_sub hv_chk
-- !x! ASSERT EQUALS("!!@v!!", "defined-in-helper") "helper_var value visible in parent"


-- =========================================================================
-- $CURRENT_SCRIPT_NAME — switches to the include inside the INCLUDE,
-- switches back to the includer after the INCLUDE returns.
-- =========================================================================

-- helper_script_name was captured inside the include.
CREATE TABLE hsn_chk (v TEXT);
INSERT INTO hsn_chk VALUES ('!!helper_script_name!!');
-- !x! select_sub hsn_chk
-- !x! ASSERT EQUALS("!!@v!!", "helper.sql") "inside the include, $CURRENT_SCRIPT_NAME was 'helper.sql'"

-- After the INCLUDE returned, $CURRENT_SCRIPT_NAME points at includes.sql.
CREATE TABLE parent_after_chk (v TEXT);
INSERT INTO parent_after_chk VALUES ('!!$current_script_name!!');
-- !x! select_sub parent_after_chk
-- !x! ASSERT EQUALS("!!@v!!", "includes.sql") "after INCLUDE returns, $CURRENT_SCRIPT_NAME is the includer"


-- =========================================================================
-- The include's row carries its own $CURRENT_SCRIPT_NAME value.
-- =========================================================================

CREATE TABLE helper_row_chk (src TEXT);
INSERT INTO helper_row_chk SELECT source FROM inc_audit WHERE label='helper-row';
-- !x! select_sub helper_row_chk
-- !x! ASSERT EQUALS("!!@src!!", "helper.sql") "row inserted by include tagged with include name"


-- === Done ============================================================
-- All assertions passed.
