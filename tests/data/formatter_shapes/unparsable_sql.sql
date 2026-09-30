-- Shapes sqlglot cannot fully parse, which the formatter must therefore leave
-- alone rather than rewrite from a partial parse.
-- Synthetic stand-ins for the production statements each bug was reported
-- from.  The rule these enforce: a clause the parser did not understand is
-- still in the output.

-- A CROSS JOIN LATERAL over a VALUES list with an ON CONFLICT tail.  The
-- DO NOTHING was silently dropped and --in-place reported the result as
-- reformatted.
INSERT INTO station (site_code, site_name)
SELECT
    g.a,
    g.b
FROM seed AS s
CROSS JOIN LATERAL (VALUES ('A-1', 'North well'), ('A-2', 'South well')) AS g(a, b)
ON CONFLICT (site_code) DO NOTHING;

-- An ON CONFLICT with an explicit DO UPDATE and an EXCLUDED reference.
INSERT INTO station (site_code, site_name)
VALUES ('A-3', 'East well')
ON CONFLICT (site_code) DO UPDATE
SET site_name = EXCLUDED.site_name
WHERE station.site_name IS DISTINCT FROM EXCLUDED.site_name;

-- A window frame with an EXCLUDE clause.
SELECT
    r.id,
    avg(r.value) OVER (
        PARTITION BY r.site_code
        ORDER BY r.sampled_on
        ROWS BETWEEN 3 PRECEDING AND CURRENT ROW EXCLUDE CURRENT ROW
    ) AS rolling_mean
FROM result AS r;

-- A composite-type field access in a GROUP BY, which the parser flattens.
SELECT
    (m.reading).undetected AS is_nondetect,
    count(*) AS n
FROM measurement AS m
GROUP BY
    (m.reading).undetected;
