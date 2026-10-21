-- HALT inside BEGIN BATCH, before END BATCH.
create table t (v text);
insert into t values ('before the batch');
-- !x! BEGIN BATCH
insert into t values ('in the batch');
-- !x! HALT
-- !x! END BATCH
