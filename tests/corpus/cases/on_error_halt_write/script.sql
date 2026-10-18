-- ON ERROR_HALT WRITE runs when an error stops the script.
-- !x! ON ERROR_HALT WRITE "halted after !!last!!" TO halt.txt
-- !x! SUB last start
create table t (id integer);
-- !x! SUB last created
select * from missing_table;
-- !x! SUB last never
