-- A BREAK that leaves a LOOP from inside BEGIN BATCH, before END BATCH.
create table t (v text);
-- !x! LOOP WHILE (TRUE)
-- !x! BEGIN BATCH
insert into t values ('in the batch');
-- !x! BREAK
-- !x! END BATCH
-- !x! END LOOP
insert into t values ('after the loop');
