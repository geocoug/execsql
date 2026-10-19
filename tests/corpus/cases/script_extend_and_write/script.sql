-- APPEND SCRIPT, EXTEND SCRIPT WITH METACOMMAND / SQL, and WRITE SCRIPT.
create table log (msg text);
-- !x! BEGIN SCRIPT first
insert into log values ('first');
-- !x! END SCRIPT
-- !x! BEGIN SCRIPT second
insert into log values ('second');
-- !x! END SCRIPT
-- !x! APPEND SCRIPT second TO first
-- !x! EXTEND SCRIPT first WITH METACOMMAND WRITE "extended" TO out.txt
-- !x! EXTEND SCRIPT first WITH SQL insert into log values ('extended sql');
-- !x! EXECUTE SCRIPT first
-- !x! WRITE SCRIPT first TO first.sql
-- !x! EXECUTE SCRIPT IF EXISTS no_such_script
-- !x! WRITE "after missing script" TO out.txt
