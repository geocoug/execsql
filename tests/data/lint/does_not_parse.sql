-- A script with block-structure errors.  Each one is a P001 on its own line,
-- and the parser recovers from it, so every other rule still checks the rest
-- of the script.  A misspelled block keyword (here `iff`) is a usual cause of
-- the structural error it leads to.  Annotations work as in invalid.sql.

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
-- expect: P001
-- !x! ENDIF
-- Lines inside a block comment or BEGIN SQL are not metacommands to check.
/*
-- !x! FROBNICATE
*/
-- !x! BEGIN SQL
-- !x! FROBNICATE
select 1;
-- !x! END SQL
-- The rules that need the whole script run too.
-- expect: V001
select * from !!no_such_variable!!;
-- expect: I001
-- !x! INCLUDE "does/not/exist.sql"
-- expect: P001
-- !x! ELSE
-- expect: P001
-- !x! LOOP WHILE (hasrows(pending))
-- expect: F001
-- !x! IF(False)
select 'never runs';
-- !x! ENDIF
