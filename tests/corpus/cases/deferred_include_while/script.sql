create table seen (n integer);
-- !x! SUB i 1
-- !x! LOOP WHILE (IS_GT(3, !{i}!))
-- !x! INCLUDE part_!{i}!.sql
-- !x! SUB_ADD i 1
-- !x! END LOOP
