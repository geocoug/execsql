-- Deferred !{var}! references are substituted when the metacommand acts, not when it is read.
create table t (n integer);
-- !x! SUB n 0
-- !x! LOOP WHILE (IS_GT(3, !{n}!))
-- !x! SUB_ADD n 1
insert into t values (!!n!!);
-- !x! END LOOP
-- !x! SUB stage one
-- !x! ON ERROR_HALT WRITE "failed at stage !{stage}!" TO halt.txt
-- !x! SUB stage two
select * from no_such_table;
