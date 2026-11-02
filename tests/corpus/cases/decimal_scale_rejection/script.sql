-- !x! ERROR_HALT OFF
-- !x! METACOMMAND_ERROR_HALT OFF
-- !x! CONNECT TO DUCKDB(FILE=:memory:, NEW) AS target
-- !x! USE target
CREATE TABLE amounts (i INTEGER, amount DECIMAL(10,2));
INSERT INTO amounts VALUES (0,42);
-- !x! IMPORT TO amounts FROM good.csv
-- !x! IMPORT TO amounts FROM bad.csv
-- !x! EXPORT amounts TO amounts.csv AS CSV
