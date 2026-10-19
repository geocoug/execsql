-- IMPORT and COPY errors with METACOMMAND_ERROR_HALT OFF, then REPLACEMENT.
create table t (id integer);
insert into t values (1);
-- !x! METACOMMAND_ERROR_HALT OFF
-- !x! IMPORT TO NEW t FROM data.csv
-- !x! IF (METACOMMAND_ERROR()) { WRITE "import to new existing table failed" TO out.txt }
-- !x! IMPORT TO t FROM no_such_file.csv
-- !x! IF (METACOMMAND_ERROR()) { WRITE "import of a missing file failed" TO out.txt }
-- !x! COPY t FROM initial TO NEW t IN initial
-- !x! IF (METACOMMAND_ERROR()) { WRITE "copy to new existing table failed" TO out.txt }
-- !x! METACOMMAND_ERROR_HALT ON
-- !x! IMPORT TO REPLACEMENT t FROM data.csv
-- !x! COPY t FROM initial TO REPLACEMENT t2 IN initial
