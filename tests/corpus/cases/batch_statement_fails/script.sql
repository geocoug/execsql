-- A statement fails inside a batch under ERROR_HALT OFF, and the batch's
-- later statements succeed.
-- !x! ERROR_HALT OFF
create table t (v text);
-- !x! BEGIN BATCH
insert into t values ('before the failure');
insert into no_such_table values (1);
insert into t values ('after the failure');
-- !x! END BATCH
-- !x! IF (SQL_ERROR()) { WRITE "after END BATCH: SQL_ERROR() true" TO out.txt }
-- !x! IF (NOT SQL_ERROR()) { WRITE "after END BATCH: SQL_ERROR() false" TO out.txt }
insert into t values ('after the batch');
