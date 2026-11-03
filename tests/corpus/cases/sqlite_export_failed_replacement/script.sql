CREATE TABLE source (v INTEGER);
INSERT INTO source VALUES (1), (-9223372036854775808);
CREATE TABLE victim (v TEXT);
INSERT INTO victim VALUES ('keep me');
-- !x! EXPORT victim TO out.db AS SQLITE
DROP TABLE victim;
CREATE VIEW victim AS SELECT abs(v) AS v FROM source;
-- !x! EXPORT victim TO out.db AS SQLITE
