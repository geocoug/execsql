-- ============================================================
-- control_flow.sql — Control flow stress test for execsql2
--
-- Exercises nested IF/ELSEIF/ELSE, ANDIF/ORIF compound
-- conditions, LOOP WHILE/UNTIL with counters, BREAK to exit
-- loops early, nested loops, and ERROR_HALT recovery.
--
-- Run manually:
--   python -m execsql tests/scripts/fixtures/control_flow.sql test.db -t l -n
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


-- === Phase 1: Nested IF/ELSEIF/ELSE (3 levels) =================

-- !x! sub tier gold

-- Level 1: tier check
-- !x! if (equals(!!tier!!, platinum))
-- !x! sub result wrong_platinum
-- !x! elseif (equals(!!tier!!, gold))

    /*
        This is a test comment block
        It is multiple lines.
    */

    -- Level 2: nested inside gold branch
    -- !x! sub discount 20
    -- !x! if (is_gt(!!discount!!, 10))

        -- Level 3: deep nesting
        -- !x! sub qualifies yes

    -- !x! else
        -- !x! sub qualifies no
    -- !x! endif

-- !x! else
-- !x! sub qualifies no
-- !x! endif

CREATE TABLE nested_if_result (qualifies TEXT, discount TEXT);
INSERT INTO nested_if_result VALUES ('!!qualifies!!', '!!discount!!');

-- !x! ASSERT EQUALS(!!qualifies!!, yes) "gold tier with discount > 10 should qualify"
-- !x! ASSERT EQUALS(!!discount!!, 20) "gold tier discount should be 20"


-- === Phase 2: ANDIF compound condition ==========================

-- !x! sub role admin
-- !x! sub active 1

-- !x! if (equals(!!role!!, admin))
-- !x! andif (equals(!!active!!, 1))
CREATE TABLE access_granted (id INTEGER);
INSERT INTO access_granted VALUES (1);
-- !x! endif

-- !x! ASSERT TABLE_EXISTS(access_granted) "admin + active should grant access"

-- Negative case: ANDIF should block when second condition fails
-- !x! sub role admin
-- !x! sub active 0

-- !x! if (equals(!!role!!, admin))
-- !x! andif (equals(!!active!!, 1))
CREATE TABLE should_not_exist_andif (id INTEGER);
-- !x! endif

-- !x! ASSERT NOT TABLE_EXISTS(should_not_exist_andif) "admin + inactive should NOT create table"


-- === Phase 3: ORIF compound condition ===========================

-- !x! sub x 0
-- !x! sub y 1

-- !x! if (equals(!!x!!, 1))
-- !x! orif (equals(!!y!!, 1))
CREATE TABLE or_result (id INTEGER);
INSERT INTO or_result VALUES (1);
-- !x! endif

-- !x! ASSERT TABLE_EXISTS(or_result) "ORIF: x=0 OR y=1 should create table"

-- Both false: ORIF should not execute
-- !x! sub x 0
-- !x! sub y 0

-- !x! if (equals(!!x!!, 1))
-- !x! orif (equals(!!y!!, 1))
CREATE TABLE should_not_exist_orif (id INTEGER);
-- !x! endif

-- !x! ASSERT NOT TABLE_EXISTS(should_not_exist_orif) "ORIF: x=0 OR y=0 should NOT create table"


-- === Phase 4: LOOP WHILE with counter ===========================

-- !x! sub counter 0

-- !x! loop while (not is_gte(!{counter}!, 10))
-- !x! sub_add counter 1
-- !x! end loop

CREATE TABLE while_result (final_count INTEGER);
INSERT INTO while_result VALUES (!!counter!!);

-- !x! ASSERT EQUALS(!!counter!!, 10) "WHILE loop should count to 10"


-- === Phase 5: LOOP UNTIL ========================================

-- !x! sub counter 0

-- !x! loop until (equals(!{counter}!, 7))
-- !x! sub_add counter 1
-- !x! end loop

CREATE TABLE until_result (final_count INTEGER);
INSERT INTO until_result VALUES (!!counter!!);

-- !x! ASSERT EQUALS(!!counter!!, 7) "UNTIL loop should stop at 7"


-- === Phase 6: LOOP with BREAK ==================================

-- !x! sub counter 0

-- !x! loop while (not is_gte(!{counter}!, 1000))
-- !x! sub_add counter 1
-- !x! if (equals(!!counter!!, 5))
-- !x! break
-- !x! endif
-- !x! end loop

CREATE TABLE break_result (final_count INTEGER);
INSERT INTO break_result VALUES (!!counter!!);

-- !x! ASSERT EQUALS(!!counter!!, 5) "BREAK should exit loop at 5"


-- NOTE: Nested loops with deferred evaluation (!{var}!) are a known
-- engine limitation and are not tested here.


-- === Phase 7: ERROR_HALT OFF/ON recovery ========================

-- !x! error_halt off
SELECT * FROM this_table_does_not_exist_xyz;
-- !x! error_halt on

CREATE TABLE survived_error (id INTEGER);
INSERT INTO survived_error VALUES (1);

-- !x! ASSERT TABLE_EXISTS(survived_error) "script should continue after error with ERROR_HALT OFF"


-- === Phase 8: Loop building a table row by row ==================

CREATE TABLE loop_data (iteration INTEGER, doubled INTEGER);

-- !x! sub i 1
-- !x! loop while (not is_gt(!{i}!, 5))
    -- !x! sub doubled !!i!!
    -- !x! sub_add doubled !!i!!
    INSERT INTO loop_data VALUES (!!i!!, !!doubled!!);
    -- !x! sub_add i 1
-- !x! end loop

-- !x! ASSERT ROW_COUNT_EQ(loop_data, 5) "loop should insert exactly 5 rows"


-- === Done =======================================================
-- If we reach here, all assertions passed.
