-- ============================================================
-- parquet_feather_roundtrip.sql — Apache Parquet and Arrow
-- Feather IMPORT/EXPORT round-trips via the polars adapter.
--
-- Both formats require the `polars` package (part of the
-- `[formats]` install extra).
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


CREATE TABLE source (id INTEGER PRIMARY KEY, name TEXT, score REAL);
INSERT INTO source VALUES (1, 'alpha',   10.5);
INSERT INTO source VALUES (2, 'bra,vo',  20.0);
INSERT INTO source VALUES (3, 'charlie', 30.75);


-- =========================================================================
-- Phase 1: Parquet round-trip
-- =========================================================================

-- !x! export source to source.parquet as parquet
-- !x! ASSERT FILE_EXISTS(source.parquet) "Parquet export created the file"

-- !x! import to new parquet_back from parquet source.parquet
-- !x! ASSERT ROW_COUNT_EQ(parquet_back, 3) "Parquet import recovered 3 rows"

-- Spot-check a string value (commas inside data fields don't matter for
-- columnar formats).
CREATE TABLE p1_chk (n TEXT);
INSERT INTO p1_chk SELECT name FROM parquet_back WHERE id='2';
-- !x! select_sub p1_chk
-- !x! ASSERT EQUALS("!!@n!!", "bra,vo") "Parquet preserves comma-containing strings"


-- =========================================================================
-- Phase 2: Feather round-trip
-- =========================================================================

-- !x! export source to source.feather as feather
-- !x! ASSERT FILE_EXISTS(source.feather) "Feather export created the file"

-- !x! import to new feather_back from feather source.feather
-- !x! ASSERT ROW_COUNT_EQ(feather_back, 3) "Feather import recovered 3 rows"

CREATE TABLE p2_chk (n TEXT);
INSERT INTO p2_chk SELECT name FROM feather_back WHERE id='2';
-- !x! select_sub p2_chk
-- !x! ASSERT EQUALS("!!@n!!", "bra,vo") "Feather preserves comma-containing strings"


-- === Done ============================================================
-- All assertions passed.
