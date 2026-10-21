-- A BREAK that leaves an inner batch but not the outer one: the outer
-- batch carries on and reaches its END BATCH.
create table t (v text);
-- !x! BEGIN SCRIPT inner
-- !x! BEGIN BATCH
insert into t values ('inner');
-- !x! BREAK
-- !x! END BATCH
-- !x! END SCRIPT
-- !x! BEGIN BATCH
insert into t values ('outer before');
-- !x! EXECUTE SCRIPT inner
insert into t values ('outer after');
-- !x! END BATCH
