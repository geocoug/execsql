-- The upstream idiom for a string literal: quotes around !'!v!'!, which
-- upstream reads as "double the apostrophes in v".
-- !x! SUB name O'Brien
create table t (n text);
insert into t values ('!'!name!'!');
-- !x! WRITE "name=!!name!!" TO vars.txt
