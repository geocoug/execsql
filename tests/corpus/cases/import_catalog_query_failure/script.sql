create table t (v text);
-- !x! ERROR_HALT OFF
-- !x! METACOMMAND_ERROR_HALT OFF
-- !x! BEGIN BATCH
insert into t values ('A');
-- !x! IMPORT TO NEW unknown_schema.destination FROM input.csv
insert into t values ('B');
-- !x! END BATCH
-- !x! IF (SQL_ERROR()) { WRITE "batch failed" TO checks.txt }
