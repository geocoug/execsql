-- IMPORT_FILE puts a whole file's contents into one column of a new row.
create table docs (body text);
-- !x! IMPORT_FILE TO TABLE docs COLUMN body FROM note.txt
