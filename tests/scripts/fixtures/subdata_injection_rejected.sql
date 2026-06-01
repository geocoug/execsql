-- ===========================================================================
-- subdata_injection_rejected.sql — SUBDATA / SELECT_SUB datasource validation
--
-- Demonstrates that SUBDATA and SELECT_SUB reject datasource arguments that
-- look like anything other than a plain `[schema.]table` identifier, so a
-- substitution variable containing SQL injection cannot reach the SELECT
-- builder.
--
-- Run with SQLite:
--   execsql tests/scripts/fixtures/subdata_injection_rejected.sql -t l /tmp/inj.db
--
-- Exit 0 = every injection variant was correctly rejected.  Exit 1 means a
-- variant slipped through and SUBDATA / SELECT_SUB executed unsafe SQL.
-- ===========================================================================

-- Setup: create a benign table the safe variants should read from.
drop table if exists greetings;
create table greetings (msg text);
insert into greetings values ('hello');

-- A "danger" table the injection attempts try to drop.  If injection works,
-- this table disappears and the final ASSERT below catches it.
drop table if exists guard;
create table guard (id int);
insert into guard values (1);

-- =========================================================================
-- 1. Happy path — plain identifier works.
-- =========================================================================
-- !x! SUBDATA happy_msg greetings
-- !x! ASSERT sub_defined(happy_msg)
-- !x! ASSERT equal("!!happy_msg!!", "hello")

-- =========================================================================
-- 2. Each of these variants must be REJECTED.  We use ON ERROR_HALT OFF so
-- the script keeps running after each rejected variant; the post-block
-- ASSERTTs then confirm the guard table is intact.
-- =========================================================================

-- !x! METACOMMAND_ERROR_HALT OFF
-- !x! ERROR_HALT OFF

-- 2a. Classic semicolon injection.
-- !x! SUB inject_a greetings; drop table guard; --
-- !x! SUBDATA r_a !!inject_a!!
-- !x! ASSERT NOT(sub_defined(r_a))

-- 2b. WHERE clause appended.
-- !x! SUB inject_b greetings WHERE 1=1
-- !x! SUBDATA r_b !!inject_b!!
-- !x! ASSERT NOT(sub_defined(r_b))

-- 2c. Subquery in place of a table name.
-- !x! SUB inject_c (select * from guard)
-- !x! SUBDATA r_c !!inject_c!!
-- !x! ASSERT NOT(sub_defined(r_c))

-- 2d. Quoted identifier with embedded space.
-- !x! SUB inject_d "my table"
-- !x! SUBDATA r_d !!inject_d!!
-- !x! ASSERT NOT(sub_defined(r_d))

-- 2e. Three-part dotted name (only `schema.table` is allowed).
-- !x! SUB inject_e a.b.c
-- !x! SUBDATA r_e !!inject_e!!
-- !x! ASSERT NOT(sub_defined(r_e))

-- 2f. SELECT_SUB with the same WHERE injection.
-- !x! SELECT_SUB greetings WHERE 1=1

-- Re-enable strict halting before the final assert so any leakage halts now.
-- !x! METACOMMAND_ERROR_HALT ON
-- !x! ERROR_HALT ON

-- =========================================================================
-- 3. Guard table must still be intact — injection variants did not run.
-- =========================================================================
-- !x! SUBDATA guard_id guard
-- !x! ASSERT equal("!!guard_id!!", "1") 'Injection variant slipped past SUBDATA / SELECT_SUB validation.'
