-- ============================================================
-- io_formats.sql — Exercise EXPORT to less-trafficked formats.
-- These produce display- or document-oriented output rather than
-- round-trippable data; assertions check that the formatter
-- runs without error and produces a non-zero output file.
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


CREATE TABLE rs (id INTEGER PRIMARY KEY, label TEXT, score REAL);
INSERT INTO rs VALUES (1, 'alpha',   10.5);
INSERT INTO rs VALUES (2, 'bravo',   20.0);
INSERT INTO rs VALUES (3, 'charlie', 30.75);


-- =========================================================================
-- Phase 1: EXPORT to TXT — plain-text formatted table
-- =========================================================================

-- !x! export rs to rs.txt as txt
-- !x! ASSERT FILE_EXISTS(rs.txt) "EXPORT AS TXT created the file"


-- =========================================================================
-- Phase 2: EXPORT to JSON — structured JSON array
-- (Already round-tripped in audit_smoke.sql; here we just confirm the
-- file appears for the canonical EXPORT AS JSON form.)
-- =========================================================================

-- !x! export rs to rs.json as json
-- !x! ASSERT FILE_EXISTS(rs.json) "EXPORT AS JSON created the file"

-- Re-import to prove the JSON is valid + round-trippable.
-- !x! import to new rs_json_back from json rs.json
-- !x! ASSERT ROW_COUNT_EQ(rs_json_back, 3) "JSON round-trip preserved 3 rows"


-- =========================================================================
-- Phase 3: EXPORT to HTML — HTML <table>
-- =========================================================================

-- !x! export rs to rs.html as html
-- !x! ASSERT FILE_EXISTS(rs.html) "EXPORT AS HTML created the file"


-- =========================================================================
-- Phase 4: EXPORT to LATEX — \begin{tabular}…\end{tabular}
-- =========================================================================

-- !x! export rs to rs.tex as latex
-- !x! ASSERT FILE_EXISTS(rs.tex) "EXPORT AS LATEX created the file"


-- =========================================================================
-- Phase 5: EXPORT to YAML and XML
-- =========================================================================

-- !x! export rs to rs.yaml as yaml
-- !x! ASSERT FILE_EXISTS(rs.yaml) "EXPORT AS YAML created the file"

-- !x! export rs to rs.xml as xml
-- !x! ASSERT FILE_EXISTS(rs.xml) "EXPORT AS XML created the file"


-- =========================================================================
-- Phase 6: EXPORT APPEND — appending to an existing CSV
-- =========================================================================

CREATE TABLE rs_more (id INTEGER PRIMARY KEY, label TEXT, score REAL);
INSERT INTO rs_more VALUES (4, 'delta', 40.0);
INSERT INTO rs_more VALUES (5, 'echo',  50.25);

-- Phase 2 already exported the base rs.json — but for CSV we need a
-- baseline export here.
-- !x! export rs to rs_combined.csv as csv

-- APPEND new rows.
-- !x! export rs_more append to rs_combined.csv as csv

-- Re-import combined file: 3 original + 2 appended = 5 rows.
-- !x! import to new rs_combined_back from rs_combined.csv
-- !x! ASSERT ROW_COUNT_EQ(rs_combined_back, 5) "EXPORT APPEND: combined file has 5 rows after both writes"


-- === Done ============================================================
-- All assertions passed.
