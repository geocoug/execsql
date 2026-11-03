-- Completed WRITE lines are visible while their background handle is still open.
CREATE TABLE snapshot(v BLOB);
CREATE TABLE observed(n INTEGER);
-- !x! WRITE "first" TO out.txt
-- !x! WAIT_UNTIL FILE_EXISTS(out.txt) HALT AFTER 5 SECONDS
-- !x! WAIT_UNTIL IS_TRUE(no) CONTINUE AFTER 1 SECONDS
-- !x! IMPORT_FILE TO TABLE snapshot COLUMN v FROM out.txt
INSERT INTO observed SELECT length(replace(CAST(v AS TEXT), char(13), '')) FROM snapshot;
DROP TABLE snapshot;
