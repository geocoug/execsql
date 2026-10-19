-- SQL_ERROR() and METACOMMAND_ERROR() report the last failure when halting is off.
create table t (id integer primary key);
-- !x! ERROR_HALT OFF
insert into t values (1);
insert into t values (1);
-- !x! IF (SQL_ERROR()) { WRITE "sql error seen" TO out.txt }
insert into t values (2);
-- !x! IF (NOT SQL_ERROR()) { WRITE "sql error cleared" TO out.txt }
-- !x! ERROR_HALT ON
-- !x! METACOMMAND_ERROR_HALT OFF
-- !x! INCLUDE missing.sql
-- !x! IF (METACOMMAND_ERROR()) { WRITE "metacommand error seen" TO out.txt }
-- !x! METACOMMAND_ERROR_HALT ON
