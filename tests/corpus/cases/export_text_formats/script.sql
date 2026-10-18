-- EXPORT to the delimited and text formats.
create table t (id integer, name text, amt real, note text);
insert into t values (1, 'Ann', 1.5, 'has, comma'), (2, 'Bob', null, 'say "hi"'), (3, 'Cé', -2, null);
-- !x! EXPORT t TO t.csv AS CSV
-- !x! EXPORT t TO t.tsv AS TSV
-- !x! EXPORT t TO t.tab AS TAB
-- !x! EXPORT t TO t.txt AS TXT
-- !x! EXPORT t TO t.plain AS PLAIN
-- !x! EXPORT t TO t.us AS US
