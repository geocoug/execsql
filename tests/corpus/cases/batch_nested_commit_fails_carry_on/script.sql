-- A nested END BATCH whose commit fails, with both halt settings OFF so
-- every run carries on: then a second nested batch, a ROLLBACK BATCH and
-- a retried insert, all inside the outer batch, and a row after it.
-- !x! ERROR_HALT OFF
-- !x! METACOMMAND_ERROR_HALT OFF
PRAGMA foreign_keys = ON;
create table parent (id integer primary key);
create table child (pid integer references parent(id) deferrable initially deferred);
create table o (v text);
-- !x! BEGIN BATCH
insert into o values ('outer before');
-- !x! BEGIN BATCH
insert into child values (99);
-- !x! END BATCH
insert into o values ('outer after inner');
-- !x! BEGIN BATCH
insert into o values ('inner2');
-- !x! END BATCH
-- !x! ROLLBACK BATCH
insert into o values ('retried');
-- !x! END BATCH
insert into o values ('after the batch');
