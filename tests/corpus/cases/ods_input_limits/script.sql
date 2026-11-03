-- !x! ERROR_HALT OFF
-- !x! METACOMMAND_ERROR_HALT OFF
CREATE TABLE t(v TEXT);
INSERT INTO t VALUES ('keep');
-- !x! IMPORT TO REPLACEMENT t FROM rows.ods SHEET s
-- !x! EXPORT t TO result.csv AS CSV
CREATE TABLE invalid_target(v TEXT);
INSERT INTO invalid_target VALUES ('invalid_keep');
-- !x! IMPORT TO REPLACEMENT invalid_target FROM invalid.ods SHEET s
-- !x! EXPORT invalid_target TO invalid-result.csv AS CSV
