-- !x! CONNECT TO DUCKDB(FILE=:memory:, NEW) AS target
-- !x! USE target
CREATE TABLE amounts(i INTEGER, v DECIMAL(38,18));
-- !x! IMPORT TO amounts FROM JSON exact.json
-- !x! EXPORT amounts TO amounts.csv AS CSV
-- !x! CONFIG EXACT_DECIMALS YES
-- !x! IMPORT TO NEW powers FROM JSON powers.jsonl
-- !x! EXPORT powers TO powers.csv AS CSV
