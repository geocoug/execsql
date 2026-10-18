-- INCLUDE runs another file in the same session; variables carry across.
-- !x! SUB from_main main
-- !x! INCLUDE part.sql
-- !x! WRITE "from_part=!!from_part!!" TO out.txt
-- !x! INCLUDE IF EXISTS missing.sql
insert into t values ('after include');
