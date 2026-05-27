-- ============================================================
-- error_handling.sql — IF SQL_ERROR() / IF METACOMMAND_ERROR()
-- detection paths under ERROR_HALT OFF and METACOMMAND_ERROR_HALT OFF.
--
-- Basic ERROR_HALT OFF recovery is already covered in control_flow.sql;
-- this fixture adds the diagnostic predicates and the
-- "ON-doesn't-clear-the-error-flag" subtlety.
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================

CREATE TABLE _audit (phase TEXT, flag TEXT);


-- =========================================================================
-- Phase 1: IF SQL_ERROR() — detect a failed SQL statement
-- =========================================================================

-- !x! error_halt off
SELECT * FROM does_not_exist_phase1;

-- The next metacommand (which is also the first after the bad SQL) must
-- evaluate SQL_ERROR() against the FAILED statement.
-- !x! if (sql_error())
INSERT INTO _audit VALUES ('phase1', 'detected');
-- !x! else
INSERT INTO _audit VALUES ('phase1', 'missed');
-- !x! endif
-- !x! error_halt on

CREATE TABLE p1_chk (got TEXT);
INSERT INTO p1_chk SELECT flag FROM _audit WHERE phase='phase1';
-- !x! select_sub p1_chk
-- !x! ASSERT EQUALS("!!@got!!", "detected") "SQL_ERROR() true after a failed SELECT"


-- =========================================================================
-- Phase 2: SQL_ERROR() must be FALSE after a successful SQL statement
-- =========================================================================

-- !x! error_halt off
SELECT 1;
-- !x! if (sql_error())
INSERT INTO _audit VALUES ('phase2', 'false-positive');
-- !x! else
INSERT INTO _audit VALUES ('phase2', 'clean');
-- !x! endif
-- !x! error_halt on

CREATE TABLE p2_chk (got TEXT);
INSERT INTO p2_chk SELECT flag FROM _audit WHERE phase='phase2';
-- !x! select_sub p2_chk
-- !x! ASSERT EQUALS("!!@got!!", "clean") "SQL_ERROR() false after a successful SELECT"


-- =========================================================================
-- Phase 3: IF METACOMMAND_ERROR() — detect a failed metacommand
-- =========================================================================

-- !x! metacommand_error_halt off
-- Trigger a metacommand failure: SELECT_SUB on a non-existent table.
-- !x! select_sub no_such_table_phase3
-- !x! if (metacommand_error())
INSERT INTO _audit VALUES ('phase3', 'detected');
-- !x! else
INSERT INTO _audit VALUES ('phase3', 'missed');
-- !x! endif
-- !x! metacommand_error_halt on

CREATE TABLE p3_chk (got TEXT);
INSERT INTO p3_chk SELECT flag FROM _audit WHERE phase='phase3';
-- !x! select_sub p3_chk
-- !x! ASSERT EQUALS("!!@got!!", "detected") "METACOMMAND_ERROR() true after a failed metacommand"


-- =========================================================================
-- Phase 4: METACOMMAND_ERROR_HALT ON does NOT clear the existing flag
-- This is the subtlety called out in the docs — the toggle is for
-- *future* errors; it leaves the prior flag intact so the IF check
-- right after still sees the failure.
-- =========================================================================

CREATE TABLE p4_seed (id INTEGER);
INSERT INTO p4_seed VALUES (1);

-- !x! metacommand_error_halt off
-- !x! select_sub no_such_table_phase4
-- !x! metacommand_error_halt on
-- The flip back to ON above must not have wiped the error flag from
-- the SELECT_SUB failure.
-- !x! if (metacommand_error())
INSERT INTO _audit VALUES ('phase4', 'flag-survived');
-- !x! else
INSERT INTO _audit VALUES ('phase4', 'flag-wiped');
-- !x! endif

CREATE TABLE p4_chk (got TEXT);
INSERT INTO p4_chk SELECT flag FROM _audit WHERE phase='phase4';
-- !x! select_sub p4_chk
-- !x! ASSERT EQUALS("!!@got!!", "flag-survived") "METACOMMAND_ERROR_HALT ON leaves the prior error flag intact"


-- =========================================================================
-- Phase 5: A successful metacommand clears the error flag
-- =========================================================================

CREATE TABLE p5_seed (id INTEGER);
INSERT INTO p5_seed VALUES (1);

-- !x! metacommand_error_halt off
-- !x! select_sub no_such_table_phase5
-- A successful metacommand follows (select_sub on a real table).
-- !x! select_sub p5_seed
-- Now the flag should reflect the LATEST metacommand (which succeeded).
-- !x! if (metacommand_error())
INSERT INTO _audit VALUES ('phase5', 'still-erroring');
-- !x! else
INSERT INTO _audit VALUES ('phase5', 'cleared');
-- !x! endif
-- !x! metacommand_error_halt on

CREATE TABLE p5_chk (got TEXT);
INSERT INTO p5_chk SELECT flag FROM _audit WHERE phase='phase5';
-- !x! select_sub p5_chk
-- !x! ASSERT EQUALS("!!@got!!", "cleared") "successful metacommand clears the METACOMMAND_ERROR flag"


-- === Done ============================================================
-- All assertions passed.
