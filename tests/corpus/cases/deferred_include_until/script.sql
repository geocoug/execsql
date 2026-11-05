create table seen (n integer);
-- !x! SUB i 1
-- !x! LOOP UNTIL (IS_GT(!{i}!, 2))
-- !x! INCLUDE part_!{i}!.sql
-- !x! SUB_ADD i 1
-- !x! END LOOP
