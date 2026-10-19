-- System variables a script can read.
create table t (id integer);
insert into t values (1), (2), (3);
-- !x! WRITE "rowcount after insert=!!$LAST_ROWCOUNT!!" TO out.txt
update t set id = id + 10 where id > 1;
-- !x! WRITE "rowcount after update=!!$LAST_ROWCOUNT!!" TO out.txt
-- !x! WRITE "last sql=!!$LAST_SQL!!" TO out.txt
-- !x! WRITE "dbms=!!$CURRENT_DBMS!! alias=!!$CURRENT_ALIAS!!" TO out.txt
-- !x! WRITE "error halt=!!$ERROR_HALT_STATE!! autocommit=!!$AUTOCOMMIT_STATE!!" TO out.txt
-- !x! WRITE "script=!!$CURRENT_SCRIPT_NAME!! line=!!$SCRIPT_LINE!!" TO out.txt
-- !x! WRITE "database=!!$CURRENT_DATABASE!!" TO out.txt
-- !x! WRITE "counter=!!$COUNTER_5!! !!$COUNTER_5!!" TO out.txt
