-- Mistakes `execsql lint` must report.  A comment of the form
--     -- expect: CODE[, CODE ...]
-- says the line right below it is reported with exactly those rule codes;
-- tests/cli/test_lint_fixtures.py checks lint reports those and nothing else.

-- !x! SUB tbl orders
-- !x! BEGIN SCRIPT refresh
refresh materialized view order_summary;
-- !x! END SCRIPT

-- ==== Unknown or malformed metacommands (P003) ================================
-- A misspelled keyword.
-- expect: P003
-- !x! WRIT "Starting the load"
-- expect: P003
-- !x! SUBB region north
-- expect: P003
-- !x! IMPORTT TO NEW staging.orders FROM "data/orders.csv"
-- The keyword is right; the rest of the line fits none of its forms.
-- expect: P003
-- !x! WRITE Starting the load
-- expect: P003
-- !x! WRITE "Configuration file not found" halt
-- expect: P003
-- !x! WRITE "Unclosed quote
-- expect: P003
-- !x! LOG ""
-- expect: P003
-- !x! EXPORT orders TOO "exports/orders.csv" AS CSV
-- expect: P003
-- !x! EXPORT orders TO "exports/orders.html" AS HTML IN ZIPFILE "exports/bundle.zip"
-- expect: P003
-- !x! IMPORT staging.orders FROM "data/orders.csv"
-- expect: P003
-- !x! CONFIG GUI_LEVEL 7
-- expect: P003
-- !x! ERROR_HALT MAYBE
-- expect: P003
-- !x! SUB_ADD tbl many
-- expect: P003
-- !x! CONNECT TO POSTGRESQL(SERVER=localhost, DB=gsidb, USER=loader, NEED_PW=TRUE) AS pg
-- expect: P003
-- !x! PROMPT MESSAGE "Waiting" CONTINUE AFTER 10 SECONDS
-- !x! IF(sql_error())
-- expect: P003
-- !x! HALT message "Stopping")
-- !x! ENDIF
-- expect: P003
-- !x! WAIT_UNTIL hasrows(orders) HALT
-- A metacommand holding a variable is only known at run time, so it is not judged.
-- !x! WRIT !!tbl!!

-- ==== Unknown or malformed conditions (P004) ==================================
-- expect: P004
-- !x! IF(hasrowz(orders))
select 1;
-- !x! ENDIF
-- expect: P004
-- !x! IF(hasrows(orders) and)
select 1;
-- !x! ENDIF
-- expect: P004
-- !x! IF((hasrows(orders))
select 1;
-- !x! ENDIF
-- expect: P004
-- !x! IF(row_count_gt(orders, many))
select 1;
-- !x! ENDIF
-- !x! IF(hasrows(orders))
-- expect: P004
-- !x! ANDIF(table_exist(staging.orders))
-- expect: P004
-- !x! ORIF(sub_defined())
select 1;
-- expect: P004
-- !x! ELSEIF(hasrows(returns) or or hasrows(orders))
select 2;
-- !x! ENDIF
-- expect: P004
-- !x! LOOP WHILE (frobnicate(pending))
select 1;
-- !x! END LOOP
-- expect: P004
-- !x! LOOP UNTIL (row_count_eq(pending))
select 1;
-- !x! END LOOP
-- expect: P004
-- !x! IF(hasrowz(orders)) { WRITE "one-line IF" }
-- expect: P003
-- !x! IF(hasrows(orders)) { WRIT "one-line IF" }
-- expect: P003, P004
-- !x! IF(hasrowz(orders)) { WRIT "one-line IF" }
-- expect: P004
-- !x! ASSERT hasrowz(orders) "orders must not be empty"
-- expect: P004
-- !x! WAIT_UNTIL file_exist("data/ready.flag") HALT AFTER 60 SECONDS
-- expect: P004
-- !x! EXECUTE SCRIPT refresh WHILE (hasrowz(orders))
-- expect: P004
-- !x! ON ERROR_HALT EXECUTE SCRIPT refresh UNTIL (sql_error)
-- A condition holding a variable is only known at run time, so it is not judged.
-- !x! IF(!!tbl!!)
select 1;
-- !x! ENDIF

-- ==== The other rules, end to end =============================================
-- expect: V001
select * from !!no_such_variable!!;
-- A system variable is spelled with $; without it, it is a user variable.
-- expect: V001
select '!!date_tag!!';
-- And a user variable spelled with $ is a different, undefined variable.
-- expect: V001
select '!!$tbl!!';
-- expect: V002
-- !x! SUB never_read 1
-- expect: I001
-- !x! INCLUDE "does/not/exist.sql"
-- expect: I002
-- !x! EXECUTE SCRIPT no_such_script
-- expect: F001
-- !x! IF(True)
select 1;
-- !x! ELSE
select 2;
-- !x! ENDIF
-- expect: F001
-- !x! IF(False)
select 3;
-- !x! ENDIF
-- !x! HALT
-- expect: F002
select 'never runs';
