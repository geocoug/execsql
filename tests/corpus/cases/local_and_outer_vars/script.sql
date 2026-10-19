-- Local (~) variables, script arguments (#) and reading an outer script's locals (+).
create table log (msg text);
-- !x! SUB_LOCAL ~where main
-- !x! BEGIN SCRIPT inner
-- !x! SUB_LOCAL ~where inner
insert into log values ('inner sees ~where=!!~where!! +where=!!+where!!');
-- !x! END SCRIPT
-- !x! BEGIN SCRIPT outer (label)
-- !x! SUB_LOCAL ~where outer
insert into log values ('outer label=!!#label!! ~where=!!~where!!');
-- !x! EXECUTE SCRIPT inner
-- !x! END SCRIPT
-- !x! EXECUTE SCRIPT outer WITH ARGS (label=L1)
insert into log values ('main ~where=!!~where!!');
