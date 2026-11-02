ATTACH 'aux.db' AS aux;
CREATE TABLE main.t (v TEXT);
CREATE TABLE aux.t (v TEXT);
INSERT INTO main.t VALUES ('main-before');
INSERT INTO aux.t VALUES ('aux-before');
-- !x! IMPORT TO aux.t FROM data.csv
CREATE TABLE main.source (v TEXT);
INSERT INTO main.source VALUES ('copied-row');
-- !x! COPY main.source FROM initial TO aux.t IN initial
