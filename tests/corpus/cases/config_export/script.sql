-- Settings that change EXPORT and WRITE output.
create table t (id integer, name text);
insert into t values (1, 'a'), (2, 'b, c');
-- !x! CONFIG QUOTE_ALL_TEXT YES
-- !x! EXPORT t TO quoted.csv AS CSV
-- !x! CONFIG QUOTE_ALL_TEXT NO
-- !x! CONFIG MAKE_EXPORT_DIRS YES
-- !x! EXPORT t TO made/dirs/t.csv AS CSV
-- !x! CONFIG WRITE_PREFIX >>
-- !x! CONFIG WRITE_SUFFIX <<
-- !x! WRITE "with prefix and suffix" TO out.txt
-- !x! CONFIG WRITE_PREFIX CLEAR
-- !x! CONFIG WRITE_SUFFIX CLEAR
-- !x! WRITE "plain again" TO out.txt
