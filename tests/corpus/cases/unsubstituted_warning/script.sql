-- The un-substituted-variable warning: silent by default, printed to stderr
-- with WRITE_WARNINGS on.
-- !x! WRITE "default: [!!not_defined!!]" TO out.txt
-- !x! CONFIG WRITE_WARNINGS YES
-- !x! WRITE "warnings on: [!!not_defined!!]" TO out.txt
create table t (v text);
insert into t values ('!!also_not_defined!!');
