-- A statement whose commit fails (a deferred foreign key), outside a
-- batch, then a statement that commits on the same connection.
-- !x! ERROR_HALT OFF
PRAGMA foreign_keys = ON;
create table parent (id integer primary key);
create table child (pid integer references parent(id) deferrable initially deferred);
insert into child values (9);
-- !x! IF (SQL_ERROR()) { WRITE "the child insert failed" TO out.txt }
insert into parent values (9);
