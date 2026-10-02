-- A script that does not parse.  `execsql lint` reports the parse error and
-- still checks each metacommand line on its own, because a misspelled block
-- keyword (here `iff`) is a usual cause of the parse error.  Annotations work
-- as in invalid.sql.

-- !x! WRITE "start"
-- expect: P004
-- !x! IF(hasrowz(orders))
-- !x! WRITE "inside"
-- !x! ENDIF
-- expect: P003
-- !x! WRIT "hey"
-- !x! IF(hasrows(orders))
-- expect: P003
-- !x! iff(hasrows(returns))
-- !x! ENDIF
-- Lines inside a block comment or BEGIN SQL are not metacommands to check.
/*
-- !x! FROBNICATE
*/
-- !x! BEGIN SQL
-- !x! FROBNICATE
select 1;
-- !x! END SQL
-- expect: P001
-- !x! ENDIF
