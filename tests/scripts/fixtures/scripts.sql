-- ============================================================
-- scripts.sql — Named subroutines: BEGIN SCRIPT / EXECUTE SCRIPT.
--
-- Covers required parameters, default values, quoted defaults,
-- IF EXISTS guards, EXEC SCRIPT / RUN SCRIPT aliases, EXTEND
-- SCRIPT, and parameter substitution via the !!#param!! form.
--
-- All assertions use -- !x! ASSERT.  Exit code 0 = all passed.
-- ============================================================


-- =========================================================================
-- Phase 1: Parameterless script — defined, then executed twice
-- =========================================================================

-- !x! begin script log_one
INSERT INTO _calls (label) VALUES ('parameterless');
-- !x! end script

CREATE TABLE _calls (label TEXT);

-- !x! execute script log_one
-- !x! execute script log_one
-- !x! ASSERT ROW_COUNT_EQ(_calls, 2) "parameterless script ran twice"


-- =========================================================================
-- Phase 2: Required parameters — !!#param!! binding
-- =========================================================================

-- !x! begin script insert_row(target_id, target_label)
INSERT INTO _calls (label) VALUES ('row-!!#target_id!!-!!#target_label!!');
-- !x! end script

-- !x! execute script insert_row with arguments (target_id=10, target_label=alpha)
-- !x! execute script insert_row with arguments (target_id=20, target_label=bravo)

CREATE TABLE rp_chk (n INTEGER);
INSERT INTO rp_chk SELECT COUNT(*) FROM _calls WHERE label='row-10-alpha';
-- !x! select_sub rp_chk
-- !x! ASSERT EQUALS("!!@n!!", "1") "required param: id=10 / label=alpha row present"


-- =========================================================================
-- Phase 3: Default parameter values — optional args fall back to defaults
-- =========================================================================

-- !x! begin script tag_row(target_id, prefix=tag, suffix=default)
INSERT INTO _calls (label) VALUES ('!!#prefix!!-!!#target_id!!-!!#suffix!!');
-- !x! end script

-- (a) Use both defaults.
-- !x! execute script tag_row with arguments (target_id=1)
-- (b) Override one default.
-- !x! execute script tag_row with arguments (target_id=2, suffix=override)
-- (c) Override both defaults.
-- !x! execute script tag_row with arguments (target_id=3, prefix=alt, suffix=last)

CREATE TABLE def_chk (got TEXT);
INSERT INTO def_chk
  SELECT GROUP_CONCAT(label, '|')
  FROM (SELECT label FROM _calls WHERE label LIKE '%-1-%' OR label LIKE '%-2-%' OR label LIKE '%-3-%'
        ORDER BY label);
-- !x! select_sub def_chk
-- !x! ASSERT EQUALS("!!@got!!", "alt-3-last|tag-1-default|tag-2-override") "default-param resolution across all 3 calls"


-- =========================================================================
-- Phase 4: Quoted default values — quotes are stripped at parse time
-- =========================================================================

-- !x! begin script note(text, decoration="*** !!")
INSERT INTO _calls (label) VALUES ('!!#decoration!!');
-- !x! end script

-- The decoration default contains spaces and the literal characters
-- "***" and "!!" — the quoter must strip the outer "" but preserve
-- the inner content verbatim.
-- !x! execute script note with arguments (text=hello)

CREATE TABLE qd_chk (n INTEGER);
INSERT INTO qd_chk SELECT COUNT(*) FROM _calls WHERE label='*** !!';
-- !x! select_sub qd_chk
-- !x! ASSERT EQUALS("!!@n!!", "1") "quoted default value: spaces + literal punctuation preserved"


-- =========================================================================
-- Phase 5: IF EXISTS — guarded execution
-- =========================================================================

-- Running tally before Phase 5: 2 + 2 + 3 + 1 = 8 rows.
-- (a) Script exists → executes normally.
-- !x! execute script if exists log_one
-- !x! ASSERT ROW_COUNT_EQ(_calls, 9) "IF EXISTS for defined script: ran (now 9 rows)"

-- (b) Script does not exist → silently skipped.
-- !x! execute script if exists no_such_script_anywhere
-- !x! ASSERT ROW_COUNT_EQ(_calls, 9) "IF EXISTS for undefined script: skipped without error"


-- =========================================================================
-- Phase 6: EXEC SCRIPT and RUN SCRIPT aliases
-- =========================================================================

-- !x! exec script log_one
-- !x! ASSERT ROW_COUNT_EQ(_calls, 10) "EXEC SCRIPT alias works"

-- !x! run script log_one
-- !x! ASSERT ROW_COUNT_EQ(_calls, 11) "RUN SCRIPT alias works"


-- =========================================================================
-- Phase 7: EXTEND SCRIPT — append more statements to an existing script
-- =========================================================================

-- !x! begin script greet
INSERT INTO _calls (label) VALUES ('greet:hello');
-- !x! end script

-- Append a second INSERT to the same script.
-- !x! extend script greet with sql INSERT INTO _calls (label) VALUES ('greet:goodbye');

-- !x! execute script greet

CREATE TABLE ext_chk (n INTEGER);
INSERT INTO ext_chk SELECT COUNT(*) FROM _calls WHERE label LIKE 'greet:%';
-- !x! select_sub ext_chk
-- !x! ASSERT EQUALS("!!@n!!", "2") "EXTEND SCRIPT: both original and appended statement ran"


-- === Done ============================================================
-- All assertions passed.
