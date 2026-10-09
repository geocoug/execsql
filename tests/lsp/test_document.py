"""INCLUDE indexing reads only what is safe to read, in a workspace that may not be trusted."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("pygls")

from execsql.lsp import document  # noqa: E402
from execsql.lsp.document import index_script, read_included  # noqa: E402


def _main(tmp_path, target: str) -> str:
    main = tmp_path / "main.sql"
    main.write_text(f"-- !x! INCLUDE {target}\nSELECT '!!region!!';\n", encoding="utf-8")
    return str(main)


def test_an_included_file_defines_variables(tmp_path):
    (tmp_path / "setup.sql").write_text("-- !x! SUB region north\n", encoding="utf-8")
    main = _main(tmp_path, "setup.sql")
    assert "REGION" in index_script((tmp_path / "main.sql").read_text(), main).definitions


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs os.mkfifo")
def test_a_fifo_is_not_opened(tmp_path):
    os.mkfifo(tmp_path / "setup.sql")  # opening it would block until a writer appears
    main = _main(tmp_path, "setup.sql")
    assert "REGION" not in index_script((tmp_path / "main.sql").read_text(), main).definitions


def test_a_device_is_not_read(tmp_path):
    assert read_included(tmp_path) is None  # a directory
    if os.path.exists("/dev/zero"):
        from pathlib import Path

        assert read_included(Path("/dev/zero")) is None


def test_an_oversized_file_is_not_read(tmp_path, monkeypatch):
    (tmp_path / "setup.sql").write_text("-- !x! SUB region north\n", encoding="utf-8")
    monkeypatch.setattr(document, "MAX_INCLUDED_BYTES", 8)
    main = _main(tmp_path, "setup.sql")
    assert "REGION" not in index_script((tmp_path / "main.sql").read_text(), main).definitions


def test_a_file_that_is_not_utf8_is_skipped(tmp_path):
    (tmp_path / "setup.sql").write_bytes(b"-- !x! SUB region \xff\xfe\n")
    main = _main(tmp_path, "setup.sql")
    assert "REGION" not in index_script((tmp_path / "main.sql").read_text(), main).definitions


def test_an_include_cycle_ends(tmp_path):
    (tmp_path / "a.sql").write_text("-- !x! SUB region north\n-- !x! INCLUDE b.sql\n", encoding="utf-8")
    (tmp_path / "b.sql").write_text("-- !x! INCLUDE a.sql\n", encoding="utf-8")
    main = _main(tmp_path, "a.sql")
    assert "REGION" in index_script((tmp_path / "main.sql").read_text(), main).definitions


def test_an_include_chain_stops_at_the_file_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(document, "MAX_INCLUDED_FILES", 3)
    for n in range(5):
        (tmp_path / f"f{n}.sql").write_text(f"-- !x! SUB v{n} x\n-- !x! INCLUDE f{n + 1}.sql\n", encoding="utf-8")
    main = _main(tmp_path, "f0.sql")
    defined = index_script((tmp_path / "main.sql").read_text(), main).definitions
    assert {"V0", "V1"} <= set(defined)  # main.sql, f0 and f1 are the three files
    assert "V2" not in defined


def test_a_variable_nested_in_another_name_is_a_reference():
    index = index_script("SELECT !!N_!!grp!!_CHECKS!!;\n", None)
    assert "grp" in [r.name for r in index.references]


def test_a_local_definition_spans_the_bare_name():
    index = index_script("-- !x! SUB ~tmp 1\n", None)
    [loc] = index.definitions["TMP"]
    assert (loc.start, loc.end) == (12, 15)


def test_uses_in_included_files_are_references_but_not_under_the_cursor(tmp_path):
    (tmp_path / "setup.sql").write_text("SELECT '!!region!!';\n", encoding="utf-8")
    main = _main(tmp_path, "setup.sql")
    index = index_script((tmp_path / "main.sql").read_text(), main)
    paths = {r.location.path for r in index.references if r.key == "REGION"}
    assert paths == {main, str(tmp_path / "setup.sql")}
    from execsql.lsp.document import variable_at

    assert variable_at(index, 0, 9) is None  # line 0 of main.sql is the INCLUDE, not setup.sql's use
