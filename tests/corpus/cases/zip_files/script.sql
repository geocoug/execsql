-- EXPORT ... IN ZIPFILE and ZIP add files to a zip archive.  (ZIP reads an input
-- file: a file the script has just written may not be complete yet.)
create table t (id integer, name text);
insert into t values (1, 'a'), (2, 'b');
-- !x! EXPORT t TO t.csv IN ZIPFILE out.zip AS CSV
-- !x! EXPORT QUERY <<select count(*) as n from t;>> APPEND TO n.txt IN ZIPFILE out.zip AS TXT
-- !x! ZIP note.txt APPEND TO ZIPFILE out.zip
