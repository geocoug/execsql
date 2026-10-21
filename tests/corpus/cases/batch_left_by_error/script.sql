-- A metacommand error inside BEGIN BATCH, with an ON ERROR_HALT script
-- that logs the error to a table.
create table t (v text);
create table error_log (msg text);
-- !x! BEGIN SCRIPT log_error
insert into error_log values ('logged by ON ERROR_HALT');
-- !x! END SCRIPT
-- !x! ON ERROR_HALT EXECUTE SCRIPT log_error
-- !x! BEGIN BATCH
insert into t values ('in the batch');
-- !x! INCLUDE missing.sql
-- !x! END BATCH
