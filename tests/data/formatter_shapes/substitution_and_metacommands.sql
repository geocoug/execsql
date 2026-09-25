-- Shapes where the formatter deleted or wrongly cased execsql's own syntax.
-- Synthetic stand-ins for the shipped upsert templates the bugs came from.

-- A conditional substitution variable standing alone in a WHERE clause.  This
-- is the pattern the upsert templates use for an optional predicate; sqlglot
-- did not recognise it as an expression and dropped it, along with the
-- trailing ORDER BY in the same statement.
-- !x! SUB_EMPTY extra_filter
SELECT
    s.id,
    s.site_code
FROM staging AS s
WHERE
    s.status = 'new'
    !!~extra_filter!!
ORDER BY
    s.site_code;

-- The same variable supplying an entire predicate, with nothing else in the
-- WHERE clause to anchor it.
SELECT
    b.id
FROM base AS b
WHERE
    !!~extra_filter!!
ORDER BY
    b.id;

-- Multi-word metacommands.  Only the first word was uppercased, leaving the
-- rest as the author typed it.
-- !x! SUB target_table staging.observation
-- !x! WRITE CREATE_TABLE !!target_table!! TO schema.sql
-- !x! RESET COUNTER 1
-- !x! SET COUNTER 1 TO 0
-- !x! PROMPT SAVEFILE MESSAGE "Where should the export go?" SUB out_path
-- !x! PROMPT OPENFILE MESSAGE "Which file should be imported?" SUB in_path

-- An inline substitution used as an identifier, which must survive verbatim.
SELECT
    o.id
FROM !!target_table!! AS o
WHERE
    o.site_code = '!!$db_name!!';
