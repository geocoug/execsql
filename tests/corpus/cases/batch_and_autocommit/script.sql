-- BEGIN BATCH / ROLLBACK, BEGIN BATCH / END BATCH, and AUTOCOMMIT OFF.
create table t (v text);
-- !x! BEGIN BATCH
insert into t values ('batch rolled back');
-- !x! ROLLBACK
-- !x! END BATCH
-- !x! BEGIN BATCH
insert into t values ('batch kept');
-- !x! END BATCH
-- !x! AUTOCOMMIT OFF
insert into t values ('autocommit off, committed');
commit;
insert into t values ('autocommit off, rolled back');
rollback;
-- !x! AUTOCOMMIT ON
insert into t values ('autocommit on');
