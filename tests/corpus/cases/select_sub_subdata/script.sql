-- SELECT_SUB and SUBDATA put query results into variables.
create table t (name text, qty integer);
insert into t values ('widget', 4), ('gadget', 7);
create view first_row as select name, qty from t order by qty limit 1;
-- !x! SELECT_SUB first_row
-- !x! WRITE "name=!!@name!! qty=!!@qty!!" TO out.txt
create view one_value as select max(qty) from t;
-- !x! SUBDATA top one_value
-- !x! WRITE "top=!!top!!" TO out.txt
