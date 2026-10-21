-- A nested END BATCH whose commit fails (a deferred foreign key) while the
-- outer batch is still open, with ERROR_HALT OFF so the run carries on.
-- !x! ERROR_HALT OFF
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
-- !x! END BATCH
insert into o values ('after both');
