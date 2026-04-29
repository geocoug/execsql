-- ============================================================
-- parse_tree.sql — Comprehensive AST parser coverage fixture
--
-- This script exercises every construct the AST parser must
-- handle correctly.  It is NOT meant to be executed against a
-- database — it is parsed with --parse-tree to verify that the
-- AST represents every structure accurately.
--
-- Usage:
--   execsql --parse-tree tests/scripts/fixtures/parse_tree.sql
--
-- Sections:
--   1.  Simple SQL statements
--   2.  Multi-line SQL
--   3.  Line continuation (backslash)
--   4.  Block comments
--   5.  Metacommands (flat)
--   6.  IF block (simple)
--   7.  IF / ELSE
--   8.  IF / ELSEIF / ELSE
--   9.  IF with ANDIF
--  10.  IF with ORIF
--  11.  IF with multiple modifiers
--  12.  Inline IF
--  13.  Nested IF
--  14.  LOOP WHILE
--  15.  LOOP UNTIL
--  16.  Nested LOOP
--  17.  LOOP with BREAK
--  18.  BEGIN BATCH / END BATCH
--  19.  ROLLBACK BATCH
--  20.  BEGIN SCRIPT / END SCRIPT
--  21.  CREATE SCRIPT (alias)
--  22.  SCRIPT with parameters
--  23.  EXECUTE SCRIPT / RUN SCRIPT / EXEC SCRIPT
--  24.  EXECUTE SCRIPT with arguments
--  25.  EXECUTE SCRIPT with loop
--  26.  EXECUTE SCRIPT IF EXISTS
--  27.  BEGIN SQL / END SQL
--  28.  BEGIN SQL with comments and metacommands
--  29.  INCLUDE
--  30.  INCLUDE IF EXISTS
--  31.  ERROR_HALT / METACOMMAND_ERROR_HALT
--  32.  ON ERROR_HALT / ON CANCEL_HALT handlers
--  33.  ASSERT
--  34.  WAIT_UNTIL
--  35.  IF inside LOOP
--  36.  LOOP inside IF
--  37.  BATCH inside IF
--  38.  SCRIPT inside IF
--  39.  Triple nesting
--  40.  Deferred variables in LOOP
--  41.  SUB / SUB_ADD / RM_SUB
--  42.  CONFIG options
--  43.  CONNECT / DISCONNECT / USE
--  44.  EXPORT / IMPORT
--  45.  PROMPT variants
--  46.  Mixed realistic workflow
-- ============================================================


-- === 1. Simple SQL statements ==================================

SELECT 1;
INSERT INTO t VALUES (1);
DELETE FROM t WHERE id = 1;


-- === 2. Multi-line SQL =========================================

SELECT
  col1,
  col2,
  col3
FROM my_table
WHERE col1 > 0
ORDER BY col2;


-- === 3. Line continuation (backslash) ==========================

SELECT \
  col1, \
  col2 \
FROM t;


-- === 4. Block comments =========================================

/* Single-line block comment */

/*
  Multi-line
  block comment
  spanning several lines
*/

SELECT 'after block comments';


-- === 5. Metacommands (flat) ====================================

-- !x! SUB myvar hello_world
-- !x! SUB_ADD counter 1
-- !x! RM_SUB myvar
-- !x! SUB_APPEND myvar _suffix
-- !x! SUB_EMPTY myvar
-- !x! RESET_COUNTER mycounter
-- !x! SET_COUNTER mycounter 10
-- !x! LOG "This is a log message"
-- !x! CD /tmp


-- === 6. IF block (simple) =====================================

-- !x! IF (TRUE)
SELECT 'if_true';
-- !x! ENDIF


-- === 7. IF / ELSE ==============================================

-- !x! IF (FALSE)
SELECT 'should_not_run';
-- !x! ELSE
SELECT 'else_branch';
-- !x! ENDIF


-- === 8. IF / ELSEIF / ELSE =====================================

-- !x! IF (EQUALS(!!tier!!, platinum))
SELECT 'platinum';
-- !x! ELSEIF (EQUALS(!!tier!!, gold))
SELECT 'gold';
-- !x! ELSEIF (EQUALS(!!tier!!, silver))
SELECT 'silver';
-- !x! ELSE
SELECT 'bronze';
-- !x! ENDIF


-- === 9. IF with ANDIF ==========================================

-- !x! IF (EQUALS(!!role!!, admin))
-- !x! ANDIF (EQUALS(!!active!!, 1))
SELECT 'admin and active';
-- !x! ENDIF


-- === 10. IF with ORIF ==========================================

-- !x! IF (EQUALS(!!x!!, 1))
-- !x! ORIF (EQUALS(!!y!!, 1))
SELECT 'x or y is 1';
-- !x! ENDIF


-- === 11. IF with multiple modifiers ============================

-- !x! IF (EQUALS(!!a!!, 1))
-- !x! ANDIF (EQUALS(!!b!!, 2))
-- !x! ORIF (EQUALS(!!c!!, 3))
SELECT 'compound condition';
-- !x! ENDIF


-- === 12. Inline IF =============================================

-- !x! IF (TRUE) { LOG "inline if fired" }
-- !x! IF (HAS_ROWS) { SUB found yes }


-- === 13. Nested IF =============================================

-- !x! IF (COND_OUTER)
    -- !x! IF (COND_MIDDLE)
        -- !x! IF (COND_INNER)
        SELECT 'deep nesting';
        -- !x! ENDIF
    -- !x! ELSE
    SELECT 'middle else';
    -- !x! ENDIF
-- !x! ELSE
SELECT 'outer else';
-- !x! ENDIF


-- === 14. LOOP WHILE ============================================

-- !x! SUB counter 0
-- !x! LOOP WHILE (NOT IS_GTE(!{counter}!, 5))
-- !x! SUB_ADD counter 1
-- !x! END LOOP


-- === 15. LOOP UNTIL ============================================

-- !x! SUB counter 0
-- !x! LOOP UNTIL (EQUALS(!{counter}!, 3))
-- !x! SUB_ADD counter 1
-- !x! ENDLOOP


-- === 16. Nested LOOP ===========================================

-- !x! LOOP WHILE (COND_OUTER)
    -- !x! LOOP UNTIL (COND_INNER)
    INSERT INTO t VALUES (1);
    -- !x! ENDLOOP
-- !x! END LOOP


-- === 17. LOOP with BREAK =======================================

-- !x! SUB counter 0
-- !x! LOOP WHILE (TRUE)
-- !x! SUB_ADD counter 1
-- !x! IF (EQUALS(!!counter!!, 10))
-- !x! BREAK
-- !x! ENDIF
-- !x! END LOOP


-- === 18. BEGIN BATCH / END BATCH ===============================

-- !x! BEGIN BATCH
INSERT INTO t VALUES (1);
INSERT INTO t VALUES (2);
INSERT INTO t VALUES (3);
-- !x! END BATCH


-- === 19. ROLLBACK BATCH =======================================

-- !x! BEGIN BATCH
INSERT INTO t VALUES (99);
-- !x! ROLLBACK BATCH
-- !x! END BATCH

-- Also test plain ROLLBACK
-- !x! BEGIN BATCH
INSERT INTO t VALUES (100);
-- !x! ROLLBACK
-- !x! END BATCH


-- === 20. BEGIN SCRIPT / END SCRIPT =============================

-- !x! BEGIN SCRIPT simple_proc
SELECT 'inside simple_proc';
-- !x! END SCRIPT

-- Named END SCRIPT
-- !x! BEGIN SCRIPT named_end
SELECT 'inside named_end';
-- !x! END SCRIPT named_end


-- === 21. CREATE SCRIPT (alias) =================================

-- !x! CREATE SCRIPT created_proc
SELECT 'inside created_proc';
-- !x! END SCRIPT


-- === 22. SCRIPT with parameters ================================

-- !x! BEGIN SCRIPT parameterized WITH PARAMETERS (tbl, col)
SELECT !!#tbl!!, !!#col!! FROM dual;
-- !x! END SCRIPT

-- Short form
-- !x! BEGIN SCRIPT short_params (x, y, z)
SELECT !!#x!! + !!#y!! + !!#z!!;
-- !x! END SCRIPT

-- PARAMS alias
-- !x! CREATE SCRIPT alias_params WITH PARAMS (a, b)
SELECT !!#a!!, !!#b!!;
-- !x! END SCRIPT


-- === 23. EXECUTE SCRIPT / RUN SCRIPT / EXEC SCRIPT =============

-- !x! EXECUTE SCRIPT simple_proc
-- !x! RUN SCRIPT simple_proc
-- !x! EXEC SCRIPT simple_proc


-- === 24. EXECUTE SCRIPT with arguments =========================

-- !x! EXECUTE SCRIPT parameterized WITH ARGS (tbl=users, col=name)
-- !x! RUN SCRIPT short_params WITH ARGUMENTS (x=1, y=2, z=3)
-- !x! EXEC SCRIPT alias_params (a='hello', b='world')


-- === 25. EXECUTE SCRIPT with loop ==============================

-- !x! EXECUTE SCRIPT simple_proc WHILE (HAS_ROWS)
-- !x! RUN SCRIPT simple_proc UNTIL (ROW_COUNT_EQ(0))


-- === 26. EXECUTE SCRIPT IF EXISTS ==============================

-- !x! EXECUTE SCRIPT IF EXISTS maybe_missing
-- !x! RUN SCRIPT IF EXISTS also_maybe_missing
-- !x! EXEC SCRIPT IF EXISTS might_not_exist


-- === 27. BEGIN SQL / END SQL ===================================

-- !x! BEGIN SQL
CREATE FUNCTION add_one(x INT) RETURNS INT AS $$
BEGIN
  RETURN x + 1;
END;
$$ LANGUAGE plpgsql;
-- !x! END SQL


-- === 28. BEGIN SQL with comments and metacommands ==============

-- !x! BEGIN SQL
-- This SQL comment should be preserved in the SQL text
SELECT 1
FROM dual
WHERE 1 = 1;
-- Another SQL comment preserved
SELECT 2;
-- !x! SUB this_metacommand_is_dropped inside_sql_block
-- !x! END SQL


-- === 29. INCLUDE ================================================

-- !x! INCLUDE helpers.sql


-- === 30. INCLUDE IF EXISTS ======================================

-- !x! INCLUDE IF EXISTS optional_setup.sql
-- !x! INCLUDE IF EXIST legacy_form.sql


-- === 31. ERROR_HALT / METACOMMAND_ERROR_HALT ===================

-- !x! ERROR_HALT OFF
SELECT * FROM nonexistent_table_xyz;
-- !x! ERROR_HALT ON
-- !x! METACOMMAND_ERROR_HALT OFF
-- !x! METACOMMAND_ERROR_HALT ON
-- !x! CANCEL_HALT ON


-- === 32. ON ERROR_HALT / ON CANCEL_HALT handlers ===============

-- !x! ON ERROR_HALT EXECUTE SCRIPT simple_proc
-- !x! ON CANCEL_HALT EXECUTE SCRIPT simple_proc
-- !x! ON ERROR_HALT WRITE "Error occurred" TO error_log.txt
-- !x! ON CANCEL_HALT WRITE "Canceled" TO cancel_log.txt
-- !x! ON ERROR_HALT WRITE CLEAR
-- !x! ON CANCEL_HALT WRITE CLEAR


-- === 33. ASSERT =================================================

-- !x! ASSERT TRUE
-- !x! ASSERT EQUALS(1, 1)
-- !x! ASSERT EQUALS(!!myvar!!, expected) "myvar should equal expected"
-- !x! ASSERT NOT FALSE


-- === 34. WAIT_UNTIL =============================================

-- !x! WAIT_UNTIL TABLE_EXISTS(results) HALT AFTER 60 SECONDS


-- === 35. IF inside LOOP ========================================

-- !x! LOOP WHILE (HAS_ROWS)
    -- !x! IF (ROW_COUNT_GT(100))
    DELETE FROM big_table LIMIT 100;
    -- !x! ELSE
    DELETE FROM big_table;
    -- !x! ENDIF
-- !x! END LOOP


-- === 36. LOOP inside IF ========================================

-- !x! IF (TABLE_EXISTS(work_queue))
    -- !x! SUB batch 0
    -- !x! LOOP WHILE (NOT IS_GT(!{batch}!, 10))
    -- !x! SUB_ADD batch 1
    INSERT INTO results SELECT * FROM work_queue LIMIT 100;
    -- !x! END LOOP
-- !x! ENDIF


-- === 37. BATCH inside IF =======================================

-- !x! IF (EQUALS(!!do_commit!!, yes))
    -- !x! BEGIN BATCH
    UPDATE accounts SET balance = balance - 100 WHERE id = 1;
    UPDATE accounts SET balance = balance + 100 WHERE id = 2;
    -- !x! END BATCH
-- !x! ENDIF


-- === 38. SCRIPT inside IF ======================================

-- !x! IF (EQUALS(!!define_helpers!!, yes))
    -- !x! BEGIN SCRIPT conditional_helper
    SELECT 'defined conditionally';
    -- !x! END SCRIPT
-- !x! ENDIF


-- === 39. Triple nesting ========================================

-- !x! LOOP WHILE (COND_A)
    -- !x! IF (COND_B)
        -- !x! BEGIN BATCH
        INSERT INTO audit_log VALUES ('nested operation');
        -- !x! END BATCH
    -- !x! ELSE
        -- !x! LOOP UNTIL (COND_C)
        SELECT 'inner loop in else';
        -- !x! ENDLOOP
    -- !x! ENDIF
-- !x! END LOOP


-- === 40. Deferred variables in LOOP ============================

-- !x! SUB i 1
-- !x! LOOP WHILE (NOT IS_GT(!{i}!, 5))
    -- !x! SUB doubled !{i}!
    -- !x! SUB_ADD doubled !{i}!
    INSERT INTO results VALUES (!{i}!, !!doubled!!);
    -- !x! SUB_ADD i 1
-- !x! END LOOP


-- === 41. SUB / SUB_ADD / RM_SUB ================================

-- !x! SUB greeting Hello
-- !x! SUB name World
-- !x! SUB_ADD counter 5
-- !x! SUB_APPEND greeting , !!name!!
-- !x! SUB_EMPTY cleared_var
-- !x! RM_SUB name
-- !x! SUB_LOCAL local_only temporary_value
-- !x! SUB_TEMPFILE tmpfile .csv
-- !x! SELECTSUB SELECT name FROM users WHERE id = 1
-- !x! SUBDATA target_var SELECT count(*) FROM t


-- === 42. CONFIG options ========================================

-- !x! CONFIG MAKE_EXPORT_DIRS Yes
-- !x! CONFIG WRITE_WARNINGS Yes
-- !x! CONFIG CONSOLE WAIT_WHEN_DONE Yes
-- !x! CONFIG CONSOLE WAIT_WHEN_ERROR Yes
-- !x! CONFIG LOG_SQL Yes
-- !x! CONFIG SCAN_LINES 1000
-- !x! TIMER ON


-- === 43. CONNECT / DISCONNECT / USE ============================

-- !x! CONNECT TO SQLITE "test.db" AS testdb
-- !x! USE testdb
-- !x! AUTOCOMMIT ON
-- !x! AUTOCOMMIT OFF
-- !x! DISCONNECT testdb


-- === 44. EXPORT / IMPORT =======================================

-- !x! EXPORT QUERY <<SELECT * FROM t>> TO CSV "output.csv"
-- !x! EXPORT QUERY <<SELECT * FROM t>> TO JSON "output.json"
-- !x! IMPORT TO NEW TABLE staging FROM CSV "input.csv"


-- === 45. PROMPT variants =======================================

-- !x! PROMPT MESSAGE "Script complete"
-- !x! PROMPT ACTION "Continue?" Continue, Abort
-- !x! PAUSE "Press any key to continue"


-- === 46. Mixed realistic workflow ==============================
--
-- A realistic ETL-like script that combines many constructs.

-- !x! SUB output_dir results/!!$DATE_TAG!!
-- !x! CONFIG MAKE_EXPORT_DIRS Yes
-- !x! ERROR_HALT OFF

-- !x! BEGIN SCRIPT load_table (src, dest)
    -- !x! IF (FILE_EXISTS(!!#src!!))
        -- !x! IMPORT TO NEW TABLE !!#dest!! FROM CSV !!#src!!
        -- !x! ASSERT TABLE_EXISTS(!!#dest!!) "Import failed for !!#src!!"
    -- !x! ELSE
        -- !x! LOG "Skipping missing file: !!#src!!"
    -- !x! ENDIF
-- !x! END SCRIPT

-- !x! BEGIN SCRIPT cleanup
    -- !x! IF (TABLE_EXISTS(staging))
    DROP TABLE staging;
    -- !x! ENDIF
    -- !x! IF (TABLE_EXISTS(temp_results))
    DROP TABLE temp_results;
    -- !x! ENDIF
-- !x! END SCRIPT

-- !x! ON ERROR_HALT EXECUTE SCRIPT cleanup
-- !x! ON CANCEL_HALT EXECUTE SCRIPT cleanup
-- !x! ERROR_HALT ON

-- !x! EXECUTE SCRIPT load_table WITH ARGS (src='data/users.csv', dest=staging)

-- !x! IF (TABLE_EXISTS(staging))
    -- !x! BEGIN BATCH
    INSERT INTO users SELECT * FROM staging WHERE valid = 1;
    DELETE FROM staging WHERE valid = 1;
    -- !x! END BATCH

    -- !x! IF (HAS_ROWS)
        -- !x! ANDIF (ROW_COUNT_GT(0))
        -- !x! EXPORT QUERY <<SELECT * FROM staging WHERE valid = 0>> TO CSV "!!output_dir!!/rejected.csv"
        -- !x! LOG "Exported rejected rows"
    -- !x! ENDIF
-- !x! ENDIF

-- !x! EXECUTE SCRIPT cleanup

SELECT 'ETL complete';
