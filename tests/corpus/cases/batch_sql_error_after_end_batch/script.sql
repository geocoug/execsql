-- SQL_ERROR() right after an END BATCH whose batch ran no SQL, when the
-- statement before the batch failed.
-- !x! ERROR_HALT OFF
insert into no_such_table values (1);
-- !x! BEGIN BATCH
-- !x! SUB x 1
-- !x! END BATCH
-- !x! IF (SQL_ERROR()) { WRITE "after END BATCH: SQL_ERROR() true" TO out.txt }
-- !x! IF (NOT SQL_ERROR()) { WRITE "after END BATCH: SQL_ERROR() false" TO out.txt }
