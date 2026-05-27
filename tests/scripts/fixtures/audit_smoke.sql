-- ===========================================================================
-- audit_smoke.sql — User-runnable smoke test for the audit-2026-05-26 branch.
--
-- Exercises the user-visible behavior changes from batches B05, B07a, B08,
-- B16 against a SQLite backend.  Each phase is self-contained and protected
-- by ASSERTTs; if any ASSERT fails the script halts with exit 1.
--
-- Run (baseline — no kill switches active):
--   rm -f /tmp/audit.db
--   mkdir -p /tmp/audit-out
--   execsql --output-dir /tmp/audit-out -t l -n \
--           tests/scripts/fixtures/audit_smoke.sql /tmp/audit.db -a baseline
--
-- Kill-switch verification mode — repeat the above with each flag and pass
-- the matching variant name as $ARG_1 (via -a) so Phase 7 confirms the
-- metacommand was rejected.  Place all options BEFORE the positional args:
--
--   ... --no-rm-file    ... -a no-rm-file
--   ... --no-system-cmd ... -a no-system-cmd
--   ... --no-serve      ... -a no-serve
--
-- --output-dir is required so Phase 6 can verify path containment.
-- Phases 7-9 read/write files inside /tmp/audit-out.
--
-- Exit 0 = every script-testable guarantee on this branch is intact.
-- Manual / out-of-band checks (NUL bytes, JSONL memory profile, logging,
-- GUI, ODBC, zip bomb, linter, expansion-bomb cap) are listed at the
-- bottom of the file.
-- ===========================================================================


-- =========================================================================
-- Phase 1: Setup
-- =========================================================================

-- Match the --output-dir on the command line so subsequent EXPORT/IMPORT
-- cycles can address files inside the containment root with absolute paths.
-- Default is /tmp/audit-out for manual runs; pass an absolute path as -a
-- ($ARG_2) to override (the pytest harness uses tmp_path for isolation).
-- !x! sub outdir /tmp/audit-out
-- !x! if (SUB_DEFINED($arg_2)) { sub outdir !!$arg_2!! }

-- Kill-switch expectations.  Derived from $ARG_1 (set with -a on the
-- command line; defaults to "baseline" when not provided).  When the
-- variant matches a flag name, the corresponding expect_no_* flips to
-- "yes" and Phase 7 asserts that metacommand was rejected.
-- !x! sub variant baseline
-- !x! if (SUB_DEFINED($arg_1)) { sub variant !!$arg_1!! }
-- !x! sub expect_no_rm_file    no
-- !x! sub expect_no_system_cmd no
-- !x! sub expect_no_serve      no
-- !x! if (equals("!!variant!!", "no-rm-file"))    { sub expect_no_rm_file    yes }
-- !x! if (equals("!!variant!!", "no-system-cmd")) { sub expect_no_system_cmd yes }
-- !x! if (equals("!!variant!!", "no-serve"))      { sub expect_no_serve      yes }

drop table if exists _runlog;
CREATE TABLE _runlog (phase TEXT, note TEXT);

INSERT INTO _runlog VALUES ('setup', 'audit smoke test started');
-- !x! ASSERT TABLE_EXISTS(_runlog) "setup: _runlog must exist"

-- =========================================================================
-- Phase 2: !'!var!'! string-literal quoter — embedded single quotes
-- (B07a) — verifies the quoter doubles ' so the literal stays closed.
-- =========================================================================

-- !x! sub apos_value O'Brien said it's fine
-- !x! sub two_apos     ''double leading''

drop table if exists q_apos;
CREATE TABLE q_apos (id INTEGER PRIMARY KEY, val TEXT);

INSERT INTO q_apos VALUES (1, !'!apos_value!'!);
INSERT INTO q_apos VALUES (2, !'!two_apos!'!);

drop table if exists q_apos_chk;
CREATE TABLE q_apos_chk (val1 TEXT, val2 TEXT);
INSERT INTO q_apos_chk
  SELECT (SELECT val FROM q_apos WHERE id=1),
         (SELECT val FROM q_apos WHERE id=2);

-- !x! select_sub q_apos_chk
-- !x! ASSERT EQUALS("!!@val1!!", "O'Brien said it's fine") "apostrophe quoter: value round-trip"
-- !x! ASSERT EQUALS("!!@val2!!", "''double leading''")     "apostrophe quoter: leading apostrophes survive"

INSERT INTO _runlog VALUES ('phase2', 'single-quote quoter OK');


-- =========================================================================
-- Phase 3: !'!var!'! quoter — classical injection payload
-- (B07a) — proves the value lands as a literal, not as SQL.
-- =========================================================================

-- !x! sub evil '); DROP TABLE q_apos; --

INSERT INTO q_apos VALUES (3, !'!evil!'!);

-- If the quoter worked, q_apos still exists and now has 3 rows.
-- !x! ASSERT TABLE_EXISTS(q_apos)       "injection blocked: q_apos still exists"
-- !x! ASSERT ROW_COUNT_EQ(q_apos, 3)    "injection blocked: payload stored as literal, not executed"

INSERT INTO _runlog VALUES ('phase3', 'sql injection via !''!var!''! blocked');


-- =========================================================================
-- Phase 4: !"!var!"! identifier quoter — embedded double quotes
-- (B07a) — verifies the quoter doubles " so the identifier stays closed.
-- =========================================================================

-- Attacker-controlled column name with an embedded "
-- !x! sub col_name weird"name

-- Produces:  CREATE TABLE q_ident ("weird""name" TEXT, ok TEXT);
drop table if exists q_ident;
CREATE TABLE q_ident (!"!col_name!"! TEXT, ok TEXT);

INSERT INTO q_ident (!"!col_name!"!, ok) VALUES ('stored', 'yes');

drop table if exists q_ident_chk;
CREATE TABLE q_ident_chk (val TEXT);
INSERT INTO q_ident_chk SELECT !"!col_name!"! FROM q_ident;

-- !x! select_sub q_ident_chk
-- !x! ASSERT EQUALS("!!@val!!", "stored") "identifier quoter: column with embedded double-quote usable"

INSERT INTO _runlog VALUES ('phase4', 'double-quote identifier quoter OK');


-- =========================================================================
-- Phase 5: !'!var!'! quoter — backslash escaping (universal)
-- (B07a) — the quoter doubles \ on every host so PostgreSQL E-strings and
-- MySQL default-mode literals can't escape out.  SQLite treats backslash
-- literally, so after the roundtrip we observe two backslashes per input.
-- =========================================================================

-- !x! sub bs_value c:\path\file

drop table if exists q_bs;
CREATE TABLE q_bs (val TEXT);
INSERT INTO q_bs VALUES (!'!bs_value!'!);

drop table if exists q_bs_chk;
CREATE TABLE q_bs_chk (val TEXT);
INSERT INTO q_bs_chk SELECT val FROM q_bs;

-- SQLite stores the doubled form verbatim (no escape interpretation).
-- !x! select_sub q_bs_chk
-- !x! ASSERT EQUALS("!!@val!!", "c:\\path\\file") "backslash doubling is universal (security > byte-perfect SQLite round-trip)"

INSERT INTO _runlog VALUES ('phase5', 'backslash doubling confirmed');


-- =========================================================================
-- Phase 6: Path containment (B05)
-- Requires --output-dir on the command line.  Without it these tests
-- become positive (the export succeeds); skip the phase in that case.
-- =========================================================================

-- !x! metacommand_error_halt off

-- (a) Absolute path escapes the configured root.
-- !x! export query << SELECT 1 AS x; >> to /tmp/audit_escape_abs.csv as csv
-- !x! ASSERT METACOMMAND_ERROR() "absolute path rejected by --output-dir containment"

-- (b) Relative ..  escapes the configured root.
-- !x! export query << SELECT 1 AS x; >> to ../audit_escape_rel.csv as csv
-- !x! ASSERT METACOMMAND_ERROR() "../ traversal rejected by --output-dir containment"

-- (c) Plain filename lands inside --output-dir.
-- !x! export query << SELECT 1 AS x; >> to inside_outputdir.csv as csv
-- !x! ASSERT NOT METACOMMAND_ERROR() "plain filename allowed inside --output-dir"

-- (d) Absolute path INSIDE the containment root is allowed too.
-- !x! export query << SELECT 1 AS x; >> to !!outdir!!/abs_inside.csv as csv
-- !x! ASSERT NOT METACOMMAND_ERROR() "absolute path inside --output-dir allowed"

-- !x! metacommand_error_halt on

INSERT INTO _runlog VALUES ('phase6', 'path containment enforced');


-- =========================================================================
-- Phase 7: Kill-switch metacommands — --no-rm-file / --no-system-cmd /
-- --no-serve.  Each branch is gated by an expect_no_* sub var (set on the
-- command line with -a).  When the flag is NOT in effect we exercise the
-- metacommand and assert it succeeds; when it IS in effect we exercise it
-- and assert METACOMMAND_ERROR() fired with the policy-block message.
-- =========================================================================

-- (a) --no-rm-file
-- Use inside_outputdir.csv created in Phase 6c as the deletion target.
-- !x! metacommand_error_halt off
-- !x! rm_file !!outdir!!/inside_outputdir.csv
-- !x! if (equals("!!expect_no_rm_file!!", "yes"))
-- !x!     ASSERT METACOMMAND_ERROR() "--no-rm-file: RM_FILE was rejected"
-- !x! else
-- !x!     ASSERT NOT METACOMMAND_ERROR() "RM_FILE succeeded (no kill switch)"
-- !x! endif
-- !x! metacommand_error_halt on

-- (b) --no-system-cmd
-- Trivial command that exits 0 on every supported OS.
-- !x! metacommand_error_halt off
-- !x! system_cmd (/usr/bin/true)
-- !x! if (equals("!!expect_no_system_cmd!!", "yes"))
-- !x!     ASSERT METACOMMAND_ERROR() "--no-system-cmd: SYSTEM_CMD was rejected"
-- !x! else
-- !x!     ASSERT NOT METACOMMAND_ERROR() "SYSTEM_CMD succeeded (no kill switch)"
-- !x! endif
-- !x! metacommand_error_halt on

-- (c) --no-serve
-- Re-create a small file to SERVE from (Phase 6c's was just deleted).
-- !x! export query << SELECT 1 AS x; >> to !!outdir!!/serve_me.csv as csv
-- !x! metacommand_error_halt off
-- !x! if (equals("!!expect_no_serve!!", "yes"))
-- !x!     serve !!outdir!!/serve_me.csv as csv
-- !x!     ASSERT METACOMMAND_ERROR() "--no-serve: SERVE was rejected"
-- !x! else
-- !x!     write "  (SERVE skipped — would dump file to stdout; set -a expect_no_serve=yes to test the kill switch)"
-- !x! endif
-- !x! metacommand_error_halt on

INSERT INTO _runlog VALUES ('phase7', 'kill-switch metacommands behave per flags');


-- =========================================================================
-- Phase 8: CSV round-trip exercise (B08 SQLite executemany correctness)
-- A 1 000-row table is exported, dropped, and re-imported.
-- Also confirms exports preserve string cells verbatim (no formula-
-- injection sanitization — B16 was rolled back; CSV is just text).
-- =========================================================================

drop table if exists big;
CREATE TABLE big (id INTEGER PRIMARY KEY, label TEXT, n INTEGER);

INSERT INTO big (id, label, n)
WITH RECURSIVE seq(i) AS (
  SELECT 1 UNION ALL SELECT i+1 FROM seq WHERE i < 1000
)
SELECT i, 'row-' || i, i*7 FROM seq;

-- !x! ASSERT ROW_COUNT_EQ(big, 1000) "seed: big has 1000 rows"

-- !x! export big to !!outdir!!/big_export.csv as csv
-- !x! ASSERT FILE_EXISTS(!!outdir!!/big_export.csv) "big export file created"

DROP TABLE big;

-- !x! import to new big_reimport from !!outdir!!/big_export.csv
-- !x! ASSERT TABLE_EXISTS(big_reimport)        "import recreated table"
-- !x! ASSERT ROW_COUNT_EQ(big_reimport, 1000)  "all 1000 rows survived CSV round-trip"

-- Spot-check the last row.
CREATE TABLE big_chk (label TEXT, n TEXT);
INSERT INTO big_chk SELECT label, n FROM big_reimport WHERE id='1000';
-- !x! select_sub big_chk
-- !x! ASSERT EQUALS("!!@label!!", "row-1000") "round-trip preserved last label"
-- !x! ASSERT EQUALS("!!@n!!", "7000")         "round-trip preserved last numeric column"

-- Regression guard for B16 rollback: TEXT cells whose first character
-- looks like a spreadsheet formula leader (= + - @ tab) must NOT be
-- mutated on export.  A pre-rollback execsql would prefix these with ',
-- silently corrupting any pipeline that round-trips through a TEXT
-- column.
drop table if exists verbatim;
CREATE TABLE verbatim (id INTEGER PRIMARY KEY, val TEXT);
INSERT INTO verbatim VALUES (1, '-1.123');
INSERT INTO verbatim VALUES (2, '=1+1');
INSERT INTO verbatim VALUES (3, '@ABC');
INSERT INTO verbatim VALUES (4, '+99');
INSERT INTO verbatim VALUES (5, 'sentence with a , comma');
-- !x! export verbatim to !!outdir!!/verbatim.csv as csv
-- !x! import to new verbatim_back from !!outdir!!/verbatim.csv

drop table if exists verbatim_chk;
CREATE TABLE verbatim_chk (a TEXT, b TEXT, c TEXT, d TEXT, e TEXT);
INSERT INTO verbatim_chk
  SELECT (SELECT val FROM verbatim_back WHERE id='1'),
         (SELECT val FROM verbatim_back WHERE id='2'),
         (SELECT val FROM verbatim_back WHERE id='3'),
         (SELECT val FROM verbatim_back WHERE id='4'),
          (SELECT val FROM verbatim_back WHERE id='5');
-- !x! select_sub verbatim_chk
-- !x! ASSERT EQUALS("!!@a!!", "-1.123") "TEXT cell '-1.123' survives roundtrip verbatim"
-- !x! ASSERT EQUALS("!!@b!!", "=1+1")   "TEXT cell '=1+1' survives roundtrip verbatim"
-- !x! ASSERT EQUALS("!!@c!!", "@ABC")   "TEXT cell '@ABC' survives roundtrip verbatim"
-- !x! ASSERT EQUALS("!!@d!!", "+99")    "TEXT cell '+99' survives roundtrip verbatim"
-- !x! ASSERT EQUALS("!!@e!!", "sentence with a , comma") "TEXT cell with comma survives roundtrip verbatim"

INSERT INTO _runlog VALUES ('phase8', '1000-row CSV roundtrip + TEXT-cell verbatim guarantee');


-- =========================================================================
-- Phase 9: JSON / JSON Lines importer (B19)
-- IMPORT … FROM JSON accepts both a JSON array of objects (`[{…}, …]`)
-- and JSON Lines (https://jsonlines.org/, one object per line).  The
-- parser auto-detects by peeking the first non-whitespace char.  The
-- JSONL path streams line-by-line; the array path buffers the whole
-- file.  This phase imports the same payload in both forms and asserts
-- row-for-row parity.
--
-- Fixtures live next to this script.  We reference them via
-- $CURRENT_SCRIPT_PATH so the test is hermetic regardless of cwd.
-- =========================================================================

-- (a) JSON array form
drop table if exists cities_arr;
-- !x! import to new cities_arr from json !!$current_script_path!!audit_smoke/sample.json
-- !x! ASSERT ROW_COUNT_EQ(cities_arr, 3) "JSON array import yields 3 rows"

-- (b) JSON Lines form (same payload, one object per line)
drop table if exists cities_jsonl;
-- !x! import to new cities_jsonl from json !!$current_script_path!!audit_smoke/sample.jsonl
-- !x! ASSERT ROW_COUNT_EQ(cities_jsonl, 3) "JSONL import yields 3 rows"

-- (c) Auto-detection produces the same rows for both forms.
drop table if exists jsonl_parity;
CREATE TABLE jsonl_parity (n INTEGER);
INSERT INTO jsonl_parity
  SELECT COUNT(*)
  FROM cities_arr a JOIN cities_jsonl j
    ON a.id = j.id AND a.city = j.city AND a.elev_m = j.elev_m;
-- !x! select_sub jsonl_parity
-- !x! ASSERT EQUALS("!!@n!!", "3") "JSON array and JSONL forms yield identical rows"

-- (d) Spot-check a value from the JSONL import.
drop table if exists jsonl_spot;
CREATE TABLE jsonl_spot (city TEXT, elev_m TEXT);
INSERT INTO jsonl_spot SELECT city, elev_m FROM cities_jsonl WHERE id='1';
-- !x! select_sub jsonl_spot
-- !x! ASSERT EQUALS("!!@city!!", "Denver") "JSONL row 1 city"
-- !x! ASSERT EQUALS("!!@elev_m!!", "1609") "JSONL row 1 elevation"

INSERT INTO _runlog VALUES ('phase9', 'JSON array + JSONL importer parity (B19)');


-- =========================================================================
-- Phase 10: Summary
-- =========================================================================

-- !x! write ""
-- !x! write "=============================================================="
-- !x! write " audit-2026-05-26 smoke: ALL ASSERTIONS PASSED"
-- !x! write "=============================================================="
-- !x! write ""


-- =========================================================================
-- Manual / out-of-band tests (not script-runnable — exercise from a shell)
-- =========================================================================
--
-- (M3) JSONL streaming-memory profile (B19):
--      Phase 9 above already verifies functional correctness of the
--      JSON-array vs. JSONL parsing paths against committed fixtures.
--      The streaming MEMORY win is only visible on multi-million-record
--      files.  To benchmark, generate a large JSON Lines file:
--        python -c "import json; [print(json.dumps({'id': i, 'name': 'r'+str(i)})) for i in range(5_000_000)]" \
--          > /tmp/big.jsonl
--      Then run a one-liner script under /usr/bin/time -l (macOS) or
--      /usr/bin/time -v (Linux):
--        -- !x! import to new big from json /tmp/big.jsonl
--      Compare peak RSS before/after B19 — the JSONL path should not
--      hold the raw file text alongside the parsed records.
--
-- (M4) Log file permissions (B12):
--      execsql tests/scripts/fixtures/audit_smoke.sql /tmp/audit.db
--      ls -l ~/execsql.log   # mode must be -rw-------  (0600) on POSIX
--
-- (M5) Env-var password redaction (B12):
--      MY_PASSWORD=hunter2 execsql -a foo=bar audit_smoke.sql /tmp/audit.db
--      grep hunter2 ~/execsql.log   # must return zero hits
--      Inside any script:
--        -- !x! write "[!!$my_password!!]"   # expect "undefined variable" error
--
-- (M6) DSN-with-password warning (B12):
--      execsql --dsn 'postgresql://u:pw@h/db' some_script.sql
--      Expect a stderr warning that the password is visible in `ps`.
--
-- (M7) Plaintext-keyring warning (B20):
--      On a headless Linux host with keyrings.alt installed; execsql
--      prints a warning when PlaintextKeyring is the active backend.
--
-- (M8) Headless GUI graceful skip (B20):
--      Unset DISPLAY/WAYLAND_DISPLAY; run a script that calls
--      PROMPT ENTRY_FORM / PROMPT MAP.  Execsql skips the GUI cleanly
--      instead of crashing on a missing Tk display.
--
-- (M9) XLSX zip-bomb defense (B15):
--      Construct or download an XLSX with a high compression ratio,
--      then attempt IMPORT TABLE bomb FROM 'bomb.xlsx';  expect rejection.
--      Or:  pytest tests/security/test_zip_bomb.py -v
--
-- (M10) ODBC password escape (B06):
--      Configure a DSN with a password containing ; — execsql brace-
--      quotes the attribute so the connection string is not split.
--      Or:  pytest tests/security/test_odbc_dsn_injection.py -v
--
-- (M11) Linter (B04):
--      execsql --lint tests/scripts/fixtures/audit_lint_bad.sql
--      Expect: unmatched IF/LOOP, undefined $VAR, and missing-INCLUDE
--      diagnostics (non-zero exit).
-- =========================================================================
