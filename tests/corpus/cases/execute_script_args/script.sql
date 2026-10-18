-- BEGIN SCRIPT / EXECUTE SCRIPT with arguments, local variables and nesting.
create table log (msg text);
-- !x! BEGIN SCRIPT add_row (what, times)
-- !x! SUB_LOCAL ~note from add_row
insert into log values ('!!#what!! x !!#times!! (!!~note!!)');
-- !x! END SCRIPT add_row
-- !x! BEGIN SCRIPT outer
-- !x! EXECUTE SCRIPT add_row WITH ARGS (what=inner, times=2)
-- !x! END SCRIPT outer
-- !x! EXECUTE SCRIPT add_row WITH ARGS (what=plain, times=1)
-- !x! EXECUTE SCRIPT outer
-- !x! SUB k 0
-- !x! BEGIN SCRIPT bump
-- !x! SUB_ADD k 1
insert into log values ('bump !!k!!');
-- !x! END SCRIPT bump
-- !x! EXECUTE SCRIPT bump
-- !x! EXECUTE SCRIPT bump
-- !x! EXECUTE SCRIPT bump
-- !x! WRITE "note outside=[!!~note!!] k=!!k!!" TO out.txt
-- !x! IF (SCRIPT_EXISTS(bump)) { WRITE "bump exists" TO out.txt }
