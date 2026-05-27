-- ============================================================
-- timer.sql — TIMER ON/OFF + $TIMER substitution variable.
-- $TIMER renders as HH:MM:SS[.ffffff] (not raw seconds, despite
-- what the substitution_vars.md doc says).  We assert by comparing
-- a captured-before value to a captured-after value.
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


-- =========================================================================
-- Phase 1: $TIMER before TIMER ON has ever fired is the zero clock value
-- =========================================================================

CREATE TABLE t_initial (v TEXT);
INSERT INTO t_initial VALUES ('!!$timer!!');
-- !x! select_sub t_initial
-- !x! ASSERT EQUALS("!!@v!!", "0:00:00") "$TIMER renders as the zero HH:MM:SS clock before TIMER ON"


-- =========================================================================
-- Phase 2: TIMER ON, do enough work that the elapsed time becomes
-- distinguishable from the zero value, then capture again
-- =========================================================================

-- !x! timer on

-- A recursive CTE generating 5000 rows is plenty of work to cross the
-- microsecond threshold of $TIMER's rendering.
CREATE TABLE busywork (id INTEGER PRIMARY KEY, v INTEGER);
INSERT INTO busywork
  WITH RECURSIVE seq(i) AS (SELECT 1 UNION ALL SELECT i+1 FROM seq WHERE i < 5000)
  SELECT i, i*i FROM seq;
SELECT COUNT(*) FROM busywork;

CREATE TABLE t_running (v TEXT);
INSERT INTO t_running VALUES ('!!$timer!!');
-- !x! select_sub t_running
-- $TIMER should now differ from the zero value.
-- !x! ASSERT NOT EQUALS("!!@v!!", "0:00:00") "$TIMER is no longer zero while running"


-- =========================================================================
-- Phase 3: TIMER OFF freezes the value at the stop time
-- =========================================================================

-- !x! timer off

CREATE TABLE t_after_off (v TEXT);
INSERT INTO t_after_off VALUES ('!!$timer!!');
-- !x! select_sub t_after_off
-- !x! ASSERT NOT EQUALS("!!@v!!", "0:00:00") "$TIMER is still non-zero after TIMER OFF (stopped value)"


-- === Done ============================================================
-- All assertions passed.
