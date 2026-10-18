-- With ERROR_HALT OFF a failed statement does not stop the script.
create table t (id integer primary key);
insert into t values (1);
-- !x! ERROR_HALT OFF
insert into t values (1);
insert into no_such_table values (1);
-- !x! ERROR_HALT ON
insert into t values (2);
-- !x! METACOMMAND_ERROR_HALT OFF
-- !x! IMPORT TO t FROM missing.csv
-- !x! METACOMMAND_ERROR_HALT ON
insert into t values (3);
-- !x! WRITE "reached the end" TO out.txt
