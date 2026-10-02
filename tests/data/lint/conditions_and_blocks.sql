-- Every conditional test, and every block construct that carries a condition,
-- nested the ways real scripts nest them.
--
-- tests/cli/test_lint_fixtures.py requires `execsql lint` to report nothing on
-- this file, and requires every conditional test in the conditional table to
-- appear here.  When you register a new conditional test, add a use of it
-- below.  Nothing here is ever executed.

-- !x! SUB site north
-- !x! SUB_EMPTY maybe_blank
-- !x! SUB threshold 10

-- ==== Each conditional test, one IF apiece ===================================
-- !x! IF(hasrows(orders))
select 'hasrows';
-- !x! ENDIF
-- !x! IF(HASROWS(staging.orders))
select 'HASROWS, schema-qualified';
-- !x! ENDIF
-- !x! IF(row_count_gt(orders, 100))
select 'row_count_gt';
-- !x! ENDIF
-- !x! IF(row_count_gte(staging.orders, 1))
select 'row_count_gte';
-- !x! ENDIF
-- !x! IF(row_count_eq(orders, 0))
select 'row_count_eq';
-- !x! ENDIF
-- !x! IF(row_count_lt(orders, 5))
select 'row_count_lt';
-- !x! ENDIF
-- !x! IF(sql_error())
select 'sql_error';
-- !x! ENDIF
-- !x! IF(dialog_canceled())
select 'dialog_canceled';
-- !x! ENDIF
-- !x! IF(metacommand_error())
select 'metacommand_error';
-- !x! ENDIF
-- !x! IF(console_on)
select 'console_on';
-- !x! ENDIF
-- !x! IF(file_exists("data/orders.csv"))
select 'file_exists';
-- !x! ENDIF
-- !x! IF(directory_exists(exports))
select 'directory_exists';
-- !x! ENDIF
-- !x! IF(schema_exists(staging))
select 'schema_exists';
-- !x! ENDIF
-- !x! IF(table_exists(staging.orders))
select 'table_exists';
-- !x! ENDIF
-- !x! IF(role_exists(loader))
select 'role_exists';
-- !x! ENDIF
-- !x! IF(view_exists(order_summary))
select 'view_exists';
-- !x! ENDIF
-- !x! IF(column_exists(order_id in staging.orders))
select 'column_exists';
-- !x! ENDIF
-- !x! IF(alias_defined(pg))
select 'alias_defined';
-- !x! ENDIF
-- !x! IF(sub_defined(site))
select 'sub_defined';
-- !x! ENDIF
-- !x! IF(sub_empty(maybe_blank))
select 'sub_empty';
-- !x! ENDIF
-- !x! IF(script_exists(refresh))
select 'script_exists';
-- !x! ENDIF
-- !x! IF(equal("!!site!!", "north"))
select 'equal';
-- !x! ENDIF
-- !x! IF(equals(north, north))
select 'equals';
-- !x! ENDIF
-- !x! IF(identical(north, "north"))
select 'identical';
-- !x! ENDIF
-- !x! IF(contains(northwest, west))
select 'contains';
-- !x! ENDIF
-- !x! IF(starts_with(northwest, north, I))
select 'starts_with';
-- !x! ENDIF
-- !x! IF(ends_with(northwest, west))
select 'ends_with';
-- !x! ENDIF
-- !x! IF(is_null(""))
select 'is_null';
-- !x! ENDIF
-- !x! IF(is_zero(0))
select 'is_zero';
-- !x! ENDIF
-- !x! IF(is_gt(11, 10))
select 'is_gt';
-- !x! ENDIF
-- !x! IF(is_gte(10, 10))
select 'is_gte';
-- !x! ENDIF
-- !x! IF(is_true(yes))
select 'is_true';
-- !x! ENDIF
-- !x! IF(is_false(no))
select 'is_false';
-- !x! ENDIF
-- !x! IF(True)
select 'a literal that is always true, with no ELSE to make unreachable';
-- !x! ENDIF
-- !x! IF(dbms(PostgreSQL))
select 'dbms';
-- !x! ENDIF
-- !x! IF(database_name(gsidb))
select 'database_name';
-- !x! ENDIF
-- !x! IF(newer_file("data/orders.csv", "exports/orders.csv"))
select 'newer_file';
-- !x! ENDIF
-- !x! IF(newer_date("data/orders.csv", 2024-01-01))
select 'newer_date';
-- !x! ENDIF

-- ==== Combining tests ==========================================================
-- !x! IF(not hasrows(orders))
select 'NOT';
-- !x! ENDIF
-- !x! IF(hasrows(orders) and table_exists(staging.orders))
select 'AND';
-- !x! ENDIF
-- !x! IF(sql_error() or metacommand_error())
select 'OR';
-- !x! ENDIF
-- !x! IF((hasrows(orders) or hasrows(returns)) and not dialog_canceled())
select 'parentheses, AND, OR and NOT together';
-- !x! ENDIF
-- !x! IF (  hasrows(orders)  )
select 'spaces around the condition';
-- !x! ENDIF
-- !x! IF(is_gt(!!threshold!!, 5))
select 'a variable inside a test';
-- !x! ENDIF

-- ==== ANDIF, ORIF, ELSEIF and ELSE =============================================
-- !x! IF(hasrows(orders))
-- !x! ANDIF(table_exists(staging.orders))
-- !x! ORIF(sub_defined(site))
select 'IF with ANDIF and ORIF';
-- !x! ELSEIF(hasrows(returns))
-- !x! ANDIF(not sql_error())
select 'ELSEIF with its own ANDIF';
-- !x! ELSEIF(row_count_eq(returns, 0))
select 'second ELSEIF';
-- !x! ELSE
select 'ELSE';
-- !x! ENDIF

-- ==== Nesting ==================================================================
-- !x! IF(hasrows(orders))
    -- !x! IF(table_exists(staging.orders))
        -- !x! IF(not hasrows(staging.orders))
            -- !x! WRITE "three levels deep"
        -- !x! ELSE
            -- !x! LOOP WHILE (hasrows(staging.orders))
                delete from staging.orders where order_id in (select order_id from staging.orders limit 100);
                -- !x! IF(sql_error())
                    -- !x! BREAK
                -- !x! ENDIF
            -- !x! END LOOP
        -- !x! ENDIF
    -- !x! ELSEIF(schema_exists(staging))
        -- !x! BEGIN BATCH
            create table staging.orders (order_id integer);
            -- !x! IF(sql_error())
                -- !x! ROLLBACK BATCH
            -- !x! ENDIF
        -- !x! END BATCH
    -- !x! ENDIF
-- !x! ENDIF

-- !x! BEGIN BATCH
-- !x! IF(hasrows(returns))
insert into returns_archive select * from returns;
-- !x! ENDIF
-- !x! END BATCH

-- ==== Loops ====================================================================
-- !x! LOOP UNTIL (row_count_eq(staging.orders, 0))
delete from staging.orders where order_id = (select min(order_id) from staging.orders);
-- !x! END LOOP
-- !x! LOOP WHILE (is_gt(!!$counter_1!!, 0))
    -- !x! LOOP WHILE (hasrows(pending))
        -- !x! IF(sql_error()) { BREAK }
        delete from pending where id = (select min(id) from pending);
    -- !x! ENDLOOP
-- !x! END LOOP

-- ==== Scripts called with conditions ===========================================
-- !x! BEGIN SCRIPT refresh
refresh materialized view order_summary;
-- !x! END SCRIPT
-- !x! BEGIN SCRIPT drain WITH PARAMETERS (table_name, batch_size=100)
delete from !!#table_name!! where id in (select id from !!#table_name!! limit !!#batch_size!!);
-- !x! END SCRIPT drain
-- !x! EXECUTE SCRIPT refresh
-- !x! EXECUTE SCRIPT IF EXISTS refresh
-- !x! EXECUTE SCRIPT drain WITH ARGUMENTS (table_name=pending) WHILE (hasrows(pending))
-- !x! RUN SCRIPT drain (table_name=staging.orders, batch_size=50) UNTIL (row_count_eq(staging.orders, 0))
-- !x! ON ERROR_HALT EXECUTE SCRIPT refresh WHILE (not sql_error())

-- ==== Conditions inside metacommands ===========================================
-- !x! IF(hasrows(orders)) { WRITE "one-line IF" }
-- !x! IF(not hasrows(orders)) { EXPORT orders TO "exports/empty.csv" AS CSV }
-- !x! ASSERT hasrows(orders)
-- !x! ASSERT row_count_gte(orders, 1) "orders must not be empty"
-- !x! WAIT_UNTIL file_exists("data/ready.flag") HALT AFTER 60 SECONDS
-- !x! WAIT_UNTIL hasrows(orders) and not sql_error() CONTINUE AFTER 5 SECONDS
