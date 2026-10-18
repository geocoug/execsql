-- A failed statement stops the script: what ran before stays, nothing after runs.
create table t (id integer primary key);
insert into t values (1);
-- !x! WRITE "before" TO out.txt
insert into t values (1);
insert into t values (2);
-- !x! WRITE "after" TO out.txt
