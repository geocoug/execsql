-- Shapes whose *string content* the formatter has rewritten.
-- Synthetic stand-ins for the production scripts each bug was reported from.
-- The corpus checks assert that formatting never alters a literal, so a
-- regression in any of these fails CI instead of arriving as a bug report.

-- PostgreSQL escape strings.  `E'\\s+'` was rewritten to `e'\s+'`, turning a
-- whitespace regex into a letter-s regex, and lost a further backslash on
-- every run.
SELECT
    regexp_replace(s.note, E'\\s+', ' ', 'g') AS squeezed,
    regexp_replace(s.note, E'\\t+', ' ', 'g') AS detabbed
FROM sample AS s;

-- A multi-line single-quoted literal inside a block.  Block indentation was
-- added to each of its lines, changing the value the database stores.
-- !x! IF(True)
    INSERT INTO note (body)
    VALUES (
        'first line
second line
third line'
    );
-- !x! ENDIF

-- An untagged dollar-quoted body that closes on its own line.  Sending a
-- completed `$$ … $$` to sqlglot exploded the signature, reordered
-- `LANGUAGE … AS`, and gained a space of indentation on every run.
CREATE FUNCTION squeeze(txt text) RETURNS text AS $$
BEGIN
    IF txt IS NULL THEN
        RETURN NULL;
    END IF;
    RETURN regexp_replace(txt, E'\\s+', ' ', 'g');
END;
$$ LANGUAGE plpgsql;

-- A tagged dollar quote.  `$body$` and `$func$` were not recognised, so the
-- IF / END IF / RETURN inside them were rewritten or collapsed.
CREATE FUNCTION classify(v numeric) RETURNS text AS $body$
BEGIN
    IF v IS NULL THEN
        RETURN 'unknown';
    ELSIF v > 0 THEN
        RETURN 'positive';
    END IF;
    RETURN 'nonpositive';
END;
$body$ LANGUAGE plpgsql;

-- A dollar-quoted body inside a block, which is where the indentation bug and
-- the dollar-quote bug meet.
-- !x! IF(True)
    DO $func$
BEGIN
    PERFORM 1;
END;
$func$;
-- !x! ENDIF
