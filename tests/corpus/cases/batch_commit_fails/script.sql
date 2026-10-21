-- END BATCH whose commit fails on the first database (a deferred foreign
-- key), with an ON ERROR_HALT script that writes to the second database.
-- !x! CONNECT TO SQLITE(FILE=b.db, NEW) AS b
-- !x! USE b
create table t (v text);
create table log (v text);
-- !x! USE initial
PRAGMA foreign_keys = ON;
create table parent (id integer primary key);
create table child (pid integer references parent(id) deferrable initially deferred);
-- !x! BEGIN SCRIPT log_error
-- !x! USE b
insert into log values ('logged by ON ERROR_HALT');
-- !x! END SCRIPT
-- !x! ON ERROR_HALT EXECUTE SCRIPT log_error
-- !x! BEGIN BATCH
insert into child values (99);
-- !x! USE b
insert into t values ('batch row on b');
-- !x! USE initial
-- !x! END BATCH
