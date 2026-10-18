-- CONNECT a second SQLite database and COPY between them.
create table src (id integer, name text, amt real, flag integer);
insert into src values (1, 'a', 1.5, 1), (2, 'b', null, 0), (3, '00701', 3, 1);
-- !x! CONNECT TO SQLITE(FILE=other.db, NEW) AS other
-- !x! COPY src FROM initial TO NEW copied IN other
-- !x! COPY QUERY <<select id, name from src where id > 1;>> FROM initial TO NEW q IN other
-- !x! USE other
create table existing (id integer, name text, amt real, flag integer);
-- !x! USE initial
-- !x! COPY src FROM initial TO existing IN other
-- !x! COPY copied FROM other TO NEW back IN initial
-- !x! USE other
-- !x! EXPORT copied TO copied.csv AS CSV
-- !x! EXPORT q TO q.csv AS CSV
-- !x! EXPORT existing TO existing.csv AS CSV
-- !x! USE initial
-- !x! DISCONNECT other
