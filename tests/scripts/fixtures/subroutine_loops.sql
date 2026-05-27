-- ============================================================
-- subroutine_loops.sql — EXECUTE SCRIPT with WHILE / UNTIL clauses.
--
-- A SCRIPT body executed repeatedly until a substitution-variable
-- condition flips.  This is the recommended pattern when the loop
-- body itself wants to mutate the loop variable.  Critically, the
-- condition must use the !{var}! deferred form so the substitution
-- re-evaluates each iteration.
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


CREATE TABLE iter_log (n INTEGER);


-- =========================================================================
-- Phase 1: EXECUTE SCRIPT … UNTIL — body runs at least once, then loops
-- until the condition becomes true (Pascal repeat..until semantics).
-- =========================================================================

-- !x! begin script tick_until
-- !x! sub_add ctr 1
INSERT INTO iter_log VALUES (!!ctr!!);
-- !x! end script

-- !x! sub ctr 0
-- !x! execute script tick_until until (is_gte(!{ctr}!, 5))

-- Body ran while ctr<5, then once more on the iteration that made ctr=5.
-- !x! ASSERT EQUALS("!!ctr!!", "5") "UNTIL: counter ends at 5"
-- !x! ASSERT ROW_COUNT_EQ(iter_log, 5) "UNTIL: body ran exactly 5 times"


-- =========================================================================
-- Phase 2: EXECUTE SCRIPT … WHILE — condition checked BEFORE each
-- iteration; if false at entry, body never runs at all.
-- =========================================================================

DELETE FROM iter_log;
-- !x! sub ctr2 0

-- Body increments ctr2 and logs.  WHILE keeps running while ctr2<3.
-- !x! begin script tick_while
-- !x! sub_add ctr2 1
INSERT INTO iter_log VALUES (!!ctr2!!);
-- !x! end script

-- !x! execute script tick_while while (not is_gte(!{ctr2}!, 3))

-- !x! ASSERT EQUALS("!!ctr2!!", "3") "WHILE: counter ends at 3"
-- !x! ASSERT ROW_COUNT_EQ(iter_log, 3) "WHILE: body ran exactly 3 times"


-- =========================================================================
-- Phase 3: WHILE with a false-at-entry condition — body never runs
-- =========================================================================

DELETE FROM iter_log;
-- !x! sub ctr3 100

-- Condition is false from the start; body should not execute.
-- !x! execute script tick_while while (not is_gte(!{ctr3}!, 3))

-- iter_log stays empty; ctr3 unchanged (tick_while increments ctr2, not ctr3).
-- !x! ASSERT ROW_COUNT_EQ(iter_log, 0) "WHILE with false-at-entry condition: body skipped"


-- =========================================================================
-- Phase 4: WITH ARGUMENTS + UNTIL — parameterized loop
-- =========================================================================

DELETE FROM iter_log;
-- !x! sub batch_ctr 0

-- !x! begin script log_batch(label)
-- !x! sub_add batch_ctr 1
INSERT INTO iter_log VALUES (!!batch_ctr!!);
-- The label argument exists for each invocation but isn't asserted here;
-- it just exercises the argument-binding code path inside the loop.
-- !x! end script

-- !x! execute script log_batch with arguments (label=tick) until (is_gte(!{batch_ctr}!, 4))

-- !x! ASSERT EQUALS("!!batch_ctr!!", "4") "WITH ARGUMENTS + UNTIL: counter ends at 4"
-- !x! ASSERT ROW_COUNT_EQ(iter_log, 4) "WITH ARGUMENTS + UNTIL: body ran exactly 4 times"


-- === Done ============================================================
-- All assertions passed.
