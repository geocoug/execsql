-- !x! CONNECT TO DUCKDB(FILE=target.duckdb, NEW) AS target
-- !x! USE target
CREATE TABLE amounts(i INTEGER, v DECIMAL(38,18));
-- !x! IMPORT TO amounts FROM JSON exact.json
-- !x! EXPORT amounts TO amounts.csv AS CSV
-- !x! CONFIG EXACT_DECIMALS YES
-- !x! IMPORT TO NEW powers FROM JSON powers.jsonl
-- !x! EXPORT powers TO powers.csv AS CSV
CREATE TABLE only_ids(i INTEGER);
-- !x! IMPORT_COMMON_COLUMNS_ONLY YES
-- !x! IMPORT TO only_ids FROM JSON ignored.json
-- !x! EXPORT only_ids TO ids.csv AS CSV
-- !x! DISCONNECT FROM target
-- !x! RM_FILE target.duckdb
