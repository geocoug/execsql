create table t (v text);
-- !x! ERROR_HALT OFF
-- !x! METACOMMAND_ERROR_HALT OFF
-- !x! BEGIN BATCH
insert into t values ('held');
-- !x! WAIT_UNTIL HASROWS(missing) CONTINUE AFTER 1 SECONDS
insert into t values ('after condition');
-- !x! END BATCH
-- !x! WRITE "after batch" TO after.txt
