create temp table temp_source (v text);
insert into temp_source values ('temporary value');
create view view_source as select 'view value' as v;
-- !x! WRITE CREATE_TABLE temp_source FROM temp_source IN initial TO ddl.sql
-- !x! WRITE CREATE_TABLE view_source FROM view_source IN initial TO ddl.sql
