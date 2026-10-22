-- SQL that a metacommand runs fails inside a batch, with both error
-- halts OFF, and the batch's later statements succeed.
-- !x! METACOMMAND_ERROR_HALT OFF
-- !x! ERROR_HALT OFF
create table t (v text);
-- !x! BEGIN BATCH
insert into t values ('before the failure');
-- !x! SUBDATA x no_such_table
insert into t values ('after the failure');
-- !x! END BATCH
-- !x! IF (SQL_ERROR()) { WRITE "after END BATCH: SQL_ERROR() true" TO out.txt }
-- !x! IF (NOT SQL_ERROR()) { WRITE "after END BATCH: SQL_ERROR() false" TO out.txt }
insert into t values ('after the batch');
