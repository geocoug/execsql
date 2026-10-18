-- EXPORT QUERY, APPEND, TEE and DESCRIPTION.
create table t (id integer, name text);
insert into t values (1, 'a'), (2, 'b'), (3, 'c');
-- !x! EXPORT QUERY <<select id, name from t where id < 3 order by id;>> TO q.csv AS CSV
-- !x! EXPORT QUERY <<select id, name from t where id = 3;>> APPEND TO q.csv AS CSV
-- !x! EXPORT t TO stdout AS CSV
-- !x! EXPORT QUERY <<select count(*) as n from t;>> TEE TO n.txt AS TXT
-- !x! EXPORT t TO d.txt AS TXT DESCRIPTION "the t table"
