-- includes_helper.sql — fixture file INCLUDEEd by includes.sql.
-- Defines two substitution variables and inserts one row into
-- a table that the parent script created.  The point is to
-- verify that:
--   1. SUB definitions in the include are visible in the includer
--   2. The include can write to tables created by the includer
--   3. $CURRENT_SCRIPT_NAME inside this file reflects THIS file,
--      not the parent

-- !x! sub helper_var defined-in-helper
-- !x! sub helper_script_name !!$current_script_name!!

INSERT INTO inc_audit VALUES ('helper-row', '!!$current_script_name!!');
