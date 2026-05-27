-- ============================================================
-- transactions.sql — BATCH / AUTOCOMMIT / ROLLBACK semantics.
--
-- Covers BEGIN BATCH, END BATCH, ROLLBACK BATCH, and the
-- interaction with ERROR_HALT OFF (continuing past a failing
-- SQL statement inside a batch).
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


-- =========================================================================
-- Phase 1: Baseline — AUTOCOMMIT (the default) persists each statement
-- =========================================================================

CREATE TABLE ledger (id INTEGER PRIMARY KEY, note TEXT);
INSERT INTO ledger VALUES (1, 'baseline');
-- !x! ASSERT ROW_COUNT_EQ(ledger, 1) "AUTOCOMMIT default: insert persists"


-- =========================================================================
-- Phase 2: BEGIN BATCH … END BATCH — batched inserts commit on END
-- =========================================================================

-- !x! begin batch
INSERT INTO ledger VALUES (2, 'in-batch-A');
INSERT INTO ledger VALUES (3, 'in-batch-B');
-- !x! end batch

-- !x! ASSERT ROW_COUNT_EQ(ledger, 3) "BATCH committed: 2 inserts now visible"


-- =========================================================================
-- Phase 3: ROLLBACK BATCH — inserts inside the batch must be reverted
-- =========================================================================

-- !x! begin batch
INSERT INTO ledger VALUES (4, 'will-be-rolled-back');
INSERT INTO ledger VALUES (5, 'also-rolled-back');
-- !x! rollback batch
-- !x! end batch

-- After rollback we should still see only the 3 rows from phases 1 & 2.
-- !x! ASSERT ROW_COUNT_EQ(ledger, 3) "ROLLBACK BATCH: in-batch inserts reverted"

-- And the specific rows are gone (not just count).
CREATE TABLE rb_check (n INTEGER);
INSERT INTO rb_check SELECT COUNT(*) FROM ledger WHERE id IN (4, 5);
-- !x! select_sub rb_check
-- !x! ASSERT EQUALS("!!@n!!", "0") "ROLLBACK BATCH: ids 4 and 5 are not present"


-- =========================================================================
-- Phase 4: ERROR_HALT OFF lets a script step past a failing SQL statement
-- inside a batch.  ROLLBACK BATCH should then revert the WHOLE batch —
-- including any prior successful inserts — back to the pre-batch state.
-- =========================================================================

-- !x! error_halt off
-- !x! begin batch
INSERT INTO ledger VALUES (6, 'good-row-before-bad-sql');
SELECT * FROM this_table_does_not_exist_42;
-- !x! rollback batch
-- !x! end batch
-- !x! error_halt on

-- The good row inserted before the bad SQL must also be reverted.
-- !x! ASSERT ROW_COUNT_EQ(ledger, 3) "ROLLBACK BATCH reverts ALL in-batch work, including pre-error inserts"


-- =========================================================================
-- Phase 5: Empty batch — BEGIN BATCH immediately followed by END BATCH
-- is a no-op (no commits/rollbacks have side effects on row counts).
-- =========================================================================

-- !x! begin batch
-- !x! end batch
-- !x! ASSERT ROW_COUNT_EQ(ledger, 3) "empty BATCH: no row-count change"


-- === Done ===========================================================
-- All assertions passed.
