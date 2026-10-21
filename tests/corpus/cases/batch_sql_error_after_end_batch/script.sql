-- SQL_ERROR() right after an END BATCH that commits, when the batch's
-- last statement failed.
-- !x! ERROR_HALT OFF
create table t (v text);
-- !x! BEGIN BATCH
insert into t values ('in the batch');
insert into no_such_table values (1);
-- !x! IF (SQL_ERROR()) { WRITE "after the failed statement: SQL_ERROR() true" TO out.txt }
-- !x! END BATCH
-- !x! IF (SQL_ERROR()) { WRITE "after END BATCH: SQL_ERROR() true" TO out.txt }
-- !x! IF (NOT SQL_ERROR()) { WRITE "after END BATCH: SQL_ERROR() false" TO out.txt }
