-- ON ERROR_HALT EXECUTE SCRIPT runs a script when an error stops the run.
create table log (msg text);
-- !x! BEGIN SCRIPT cleanup
-- !x! WRITE "cleanup ran" TO cleanup.txt
-- !x! END SCRIPT
-- !x! ON ERROR_HALT EXECUTE SCRIPT cleanup
insert into log values ('before');
insert into no_such_table values (1);
insert into log values ('after');
