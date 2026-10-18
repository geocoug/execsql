-- Substitution variables: define, append, add, empty, remove, nested names.
-- !x! SUB greeting Hello
-- !x! SUB_APPEND greeting World
-- !x! SUB n 5
-- !x! SUB_ADD n 3
-- !x! SUB_ADD n -10
-- !x! SUB_EMPTY blank
-- !x! SUB temp gone
-- !x! RM_SUB temp
-- !x! SUB which two
-- !x! SUB var_two second
-- !x! WRITE "greeting=[!!greeting!!]" TO vars.txt
-- !x! WRITE "n=[!!n!!]" TO vars.txt
-- !x! WRITE "blank=[!!blank!!]" TO vars.txt
-- !x! WRITE "temp=[!!temp!!]" TO vars.txt
-- !x! WRITE "nested=[!!var_!!which!!!!]" TO vars.txt
create table t (k text, v text);
insert into t values ('greeting', '!!greeting!!'), ('n', '!!n!!');
