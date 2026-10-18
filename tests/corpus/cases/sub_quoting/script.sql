-- Quoted substitution: !'!v!'! makes a string literal, !"!v!"! an identifier.
-- !x! SUB name O'Brien
-- !x! SUB col first col
create table t (!"!col!"! text, n text);
insert into t values (!'!name!'!, 'x');
-- !x! WRITE "name=!!name!!" TO vars.txt
