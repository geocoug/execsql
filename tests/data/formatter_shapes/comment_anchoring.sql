-- Shapes that have relocated a comment out of its expression.
-- Synthetic stand-ins for the production scripts the bugs were reported from;
-- every one of these was a formatter bug before it was a fixture.
-- Deliberately left unformatted: the bugs appear on the first pass over
-- source shaped this way, so `execsql-format --check` reports it.

-- A parenthesised composite-field access inside a function call.  sqlglot
-- reflows the COALESCE across lines and used to carry the comment onto the
-- `).flag, FALSE)` continuation line.
SELECT
    m.id,
    -- non-detects are reported without a value
    COALESCE((m.reading).undetected, FALSE) AS is_nondetect
FROM measurement AS m;

-- The same access inside a CASE.  sqlglot drops comments inside CASE
-- entirely, so these come back through token matching.
SELECT
    m.id,
    CASE
        -- non-detects screen as U
        WHEN (m.reading).undetected THEN 'U'
        ELSE 'D'
    END AS screen_status
FROM measurement AS m;

-- Two comments stacked on a statement whose SQL line ends in a semicolon.
-- Removing the marker run left `1 = 1 ;` and cost a second pass.
SELECT
    s.id
FROM sample AS s
WHERE
    -- uncomment to restrict to unmatched rows
    -- and s.match_id is null
    1 = 1;

-- Comments that genuinely live inside parentheses must stay inside them.
INSERT INTO station (
    -- natural key
    site_code,
    -- descriptive
    site_name
)
VALUES
    ('A-1', 'North well');

SELECT
    r.id
FROM result AS r
WHERE
    (
        -- only validated rows
        r.status = 'V'
        AND r.value IS NOT NULL
    );
