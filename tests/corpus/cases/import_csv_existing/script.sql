-- IMPORT into tables that already exist.
create table t (id integer, code text, amount numeric, day date, note text);
-- !x! IMPORT TO t FROM data.csv
create table common (id integer, note text);
-- !x! IMPORT_COMMON_COLUMNS_ONLY YES
-- !x! IMPORT TO common FROM data.csv
