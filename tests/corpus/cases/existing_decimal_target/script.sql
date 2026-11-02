-- !x! CONNECT TO DUCKDB(FILE=:memory:, NEW) AS target
-- !x! USE target
CREATE TABLE precise (i INTEGER, v DECIMAL(38,30));
-- !x! IMPORT TO precise FROM rows.csv
-- !x! EXPORT precise TO result.csv AS CSV
CREATE TABLE microscopic (i INTEGER, v DECIMAL(38,38));
-- !x! IMPORT TO microscopic FROM tiny.csv
-- !x! EXPORT microscopic TO tiny-result.csv AS CSV
