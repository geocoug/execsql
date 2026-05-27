-- audit_lint_bad.sql — intentionally broken script for testing --lint.
-- Run:  execsql --lint tests/scripts/fixtures/audit_lint_bad.sql
-- Expect: at least two diagnostics.

-- (1) Reference to an undefined substitution variable.
SELECT !!totally_made_up_var!!;

-- (2) INCLUDE of a file that does not exist.
-- !x! include /tmp/this_file_does_not_exist_98765.sql

-- (3) Reference to an undefined substitution variable in an INCLUDE statement.
-- This should be ignored by --lint, but would cause an error if the script were actually run.
-- !x! sub script_dir /tmp
-- !x! include !!script_dir!!/this_file_does_not_exist_98765.sql
