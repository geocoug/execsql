-- EXPORT to JSON, JSON table schema, VALUES and LaTeX.
create table t (id integer, name text, amt real, day text);
insert into t values (1, 'Ann', 1.5, '2024-01-05'), (2, 'O''Neil', null, null);
-- !x! EXPORT t TO t.json AS JSON
-- !x! EXPORT t TO t_schema.json AS JSON_TS
-- !x! EXPORT t TO t_values.sql AS VALUES
-- !x! EXPORT t TO t.tex AS LATEX
