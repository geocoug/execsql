-- A BREAK out of a batch while AUTOCOMMIT is OFF: the script's own
-- commit decides what is kept.
create table t (v text);
-- !x! AUTOCOMMIT OFF
insert into t values ('held before the batch');
-- !x! LOOP WHILE (TRUE)
-- !x! BEGIN BATCH
insert into t values ('in the batch');
-- !x! BREAK
-- !x! END BATCH
-- !x! END LOOP
-- !x! AUTOCOMMIT ON WITH COMMIT
insert into t values ('after');
