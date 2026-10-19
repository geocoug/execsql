-- More conditions: files, columns, views, aliases, empty variables and combinations.
create table t (id integer, name text);
create view v as select * from t;
insert into t values (1, 'a');
-- !x! CONNECT TO SQLITE(FILE=other.db, NEW) AS other
-- !x! SUB_EMPTY empty_var
-- !x! IF (ALIAS_DEFINED(other)) { WRITE "alias other defined" TO out.txt }
-- !x! IF (NOT ALIAS_DEFINED(nope)) { WRITE "alias nope undefined" TO out.txt }
-- !x! IF (COLUMN_EXISTS(name IN t)) { WRITE "column name exists" TO out.txt }
-- !x! IF (NOT COLUMN_EXISTS(zz IN t)) { WRITE "column zz missing" TO out.txt }
-- !x! IF (VIEW_EXISTS(v)) { WRITE "view v exists" TO out.txt }
-- !x! IF (FILE_EXISTS(marker.txt)) { WRITE "marker exists" TO out.txt }
-- !x! IF (NOT FILE_EXISTS(nothing.txt)) { WRITE "nothing.txt missing" TO out.txt }
-- !x! IF (DIRECTORY_EXISTS(.)) { WRITE "dot is a directory" TO out.txt }
-- !x! IF (SUB_EMPTY(empty_var)) { WRITE "empty_var is empty" TO out.txt }
-- !x! IF (IS_GTE(3, 3)) { WRITE "3 >= 3" TO out.txt }
-- !x! IF (IS_GT(10, 9)) { WRITE "10 > 9 as numbers" TO out.txt }
-- !x! IF (CONTAINS("HayStack", "stack", I)) { WRITE "contains, ignoring case" TO out.txt }
-- !x! IF (NOT CONTAINS("HayStack", "stack")) { WRITE "not contains, with case" TO out.txt }
-- !x! IF (EQUAL("a", "b") OR EQUAL("c", "c")) { WRITE "or" TO out.txt }
-- !x! IF (NOT (EQUAL("a", "b") OR EQUAL("c", "d"))) { WRITE "not or" TO out.txt }
-- !x! IF (EQUAL("a", "a") AND NOT EQUAL("b", "c")) { WRITE "and not" TO out.txt }
-- !x! IF (IS_TRUE(1)) { WRITE "1 is true" TO out.txt }
-- !x! IF (IS_TRUE(Yes)) { WRITE "Yes is true" TO out.txt }
-- !x! IF (NOT IS_TRUE(no)) { WRITE "no is not true" TO out.txt }
-- !x! IF (NOT IS_ZERO(0.5)) { WRITE "0.5 is not zero" TO out.txt }
-- !x! IF (NOT SCHEMA_EXISTS(main)) { WRITE "no schemas on SQLite" TO out.txt }
-- !x! IF (EQUAL("10", "10.00")) { WRITE "10 equals 10.00" TO out.txt }
-- !x! IF (EQUAL("true", "yes")) { WRITE "true equals yes" TO out.txt }
-- !x! DISCONNECT other
