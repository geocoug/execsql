-- BEGIN SQL / END SQL: a statement whose body has semicolons at line ends.
create table t (v text);
create table audit (msg text);
-- !x! BEGIN SQL
create trigger t_ins after insert on t
begin
    insert into audit values ('inserted ' || new.v);
end;
-- !x! END SQL
insert into t values ('a');
insert into t values ('b');
