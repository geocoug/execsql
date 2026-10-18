-- A value with a backslash in quoted substitution.  Upstream passes the
-- value to re.sub as a replacement, so "\d" is read as a bad escape and the
-- statement fails; execsql2 stores the value.
-- !x! SUB path C:\data\new
create table t (p text);
insert into t values (!'!path!'!);
-- !x! WRITE "path=!!path!!" TO vars.txt
