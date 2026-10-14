"""The index cache: a request reparses only the files whose text changed."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pytest.importorskip("pygls")

import execsql.lsp.cache as cache_module  # noqa: E402
from execsql.lsp.cache import IndexCache  # noqa: E402
from execsql.lsp.document import file_facts, index_script  # noqa: E402
from execsql.lsp.server import ExecsqlLanguageServer  # noqa: E402


def _server(monkeypatch, source: str) -> ExecsqlLanguageServer:
    server = ExecsqlLanguageServer()
    document = SimpleNamespace(source=source, version=1)
    workspace = SimpleNamespace(get_text_document=lambda uri: document, text_documents={}, root_path=None)
    monkeypatch.setattr(ExecsqlLanguageServer, "workspace", property(lambda self: workspace))
    return server


def _counting(monkeypatch) -> dict[str, int]:
    calls = {"read": 0, "parse": 0}

    def read(path):
        calls["read"] += 1
        return cache_module_read(path)

    def parse(source, path, base_dir=None):
        calls["parse"] += 1
        return file_facts(source, path, base_dir)

    cache_module_read = cache_module.read_included
    monkeypatch.setattr(cache_module, "read_included", read)
    monkeypatch.setattr(cache_module, "file_facts", parse)
    return calls


def _includes(tmp_path, count: int, lines: int) -> str:
    body = "".join(f"SELECT {n} AS col_{n} FROM some_table WHERE id = '!!id!!';\n" for n in range(lines))
    for n in range(count):
        (tmp_path / f"part{n}.sql").write_text(f"-- !x! SUB part_{n} {n}\n{body}")
    return "".join(f"-- !x! INCLUDE part{n}.sql\n" for n in range(count)) + "SELECT '!!part_0!!';\n"


def test_a_second_request_neither_rereads_nor_reparses_unchanged_includes(monkeypatch, tmp_path):
    main = tmp_path / "main.sql"
    source = _includes(tmp_path, 50, 3000)
    server = _server(monkeypatch, source)
    calls = _counting(monkeypatch)

    first = server.index(main.as_uri())
    assert calls == {"read": 50, "parse": 51}
    second = server.index(main.as_uri())
    assert calls == {"read": 50, "parse": 51}
    assert second.definitions == first.definitions
    assert "PART_49" in second.definitions


def test_an_edit_reparses_only_the_edited_document(monkeypatch, tmp_path):
    main = tmp_path / "main.sql"
    server = _server(monkeypatch, _includes(tmp_path, 3, 10))
    calls = _counting(monkeypatch)
    server.index(main.as_uri())
    server.workspace.get_text_document(main.as_uri()).source += "-- !x! SUB extra 1\n"
    index = server.index(main.as_uri())
    assert calls == {"read": 3, "parse": 5}
    assert "EXTRA" in index.definitions


def test_a_changed_included_file_is_read_again(monkeypatch, tmp_path):
    main = tmp_path / "main.sql"
    server = _server(monkeypatch, "-- !x! INCLUDE setup.sql\n")
    setup = tmp_path / "setup.sql"
    setup.write_text("-- !x! SUB before 1\n")
    assert "BEFORE" in server.index(main.as_uri()).definitions
    setup.write_text("-- !x! SUB after_the_edit 1\n")
    os.utime(setup, ns=(setup.stat().st_atime_ns, setup.stat().st_mtime_ns + 1_000_000))
    definitions = server.index(main.as_uri()).definitions
    assert "AFTER_THE_EDIT" in definitions
    assert "BEFORE" not in definitions


def test_a_file_the_client_reports_changed_is_read_again_even_with_the_same_size_and_time(monkeypatch, tmp_path):
    main = tmp_path / "main.sql"
    server = _server(monkeypatch, "-- !x! INCLUDE setup.sql\n")
    setup = tmp_path / "setup.sql"
    setup.write_text("-- !x! SUB aaa 1\n")
    stamp = setup.stat()
    assert "AAA" in server.index(main.as_uri()).definitions
    setup.write_text("-- !x! SUB bbb 1\n")
    os.utime(setup, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    server.cache.forget(str(setup))
    assert "BBB" in server.index(main.as_uri()).definitions


def test_a_script_reading_an_ini_file_sees_the_ini_file_change(monkeypatch, tmp_path):
    main = tmp_path / "main.sql"
    (tmp_path / "vars.ini").write_text("[s]\nfirst = 1\n")
    server = _server(monkeypatch, "-- !x! SUB_INI vars.ini SECTION s\n")
    assert "FIRST" in server.index(main.as_uri()).definitions
    (tmp_path / "vars.ini").write_text("[s]\nsecond_key = 2\n")
    assert "SECOND_KEY" in server.index(main.as_uri()).definitions


def test_the_cached_index_equals_the_uncached_one(tmp_path):
    (tmp_path / "inner.sql").write_text(
        "-- !x! SUB inner 1\n-- !x! BEGIN SCRIPT s WITH PARAMS (a)\n-- !x! END SCRIPT\n",
    )
    (tmp_path / "setup.sql").write_text("-- !x! INCLUDE inner.sql\nSELECT '!!inner!!';\n")
    source = "-- !x! INCLUDE setup.sql\n-- !x! EXECUTE SCRIPT s WITH (a=1)\nSELECT '!!Inner!!', '!{x}!';\n"
    path = str(tmp_path / "main.sql")
    cache = IndexCache()
    plain = index_script(source, path)
    assert index_script(source, path, cache.text, cache.facts) == plain
    assert index_script(source, path, cache.text, cache.facts) == plain
    assert plain.script_params == {"s": ["a"]}


def test_the_cache_holds_no_more_than_its_limit(tmp_path):
    cache = IndexCache(max_chars=100)
    for n in range(10):
        path = tmp_path / f"f{n}.sql"
        path.write_text("x" * 30)
        cache.facts(cache.text(path) or "", str(path))
    assert cache._chars <= 100
