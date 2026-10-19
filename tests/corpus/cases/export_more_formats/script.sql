-- More EXPORT formats: quoted delimited, raw, base64 (decoded to binary) and XML.
create table t (id integer, name text, note text);
insert into t values (1, 'Ann', 'has "quotes"'), (2, 'Bob', null);
create table b (data text);
insert into b values ('aGVsbG8gd29ybGQ=');
-- !x! EXPORT t TO t.tabq AS TABQ
-- !x! EXPORT t TO t.tsvq AS TSVQ
-- !x! EXPORT QUERY <<select name from t where id = 1;>> TO name.raw AS RAW
-- !x! EXPORT b TO b.b64 AS B64
-- !x! EXPORT t TO t.xml AS XML
