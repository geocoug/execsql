"""The glossary templates: build a custom glossary from a master glossary table."""

from __future__ import annotations

from .conftest import known_bug, read_csv

MASTER = [
    ("site_id", "Site identifier"),
    ("sample_date", "Date the sample was collected"),
    ("result", "Measured value"),
    ("unused", "A term nobody asks for"),
]


def _master(target) -> str:
    table = target.table(target.base, "master")
    target.execute(
        f"create table {table} (term varchar(40) primary key, definition varchar(200))",
        *(f"insert into {table} values ('{t}', '{d}')" for t, d in MASTER),
    )
    return table


def _init(table: str) -> str:
    return (
        "-- !x! EXECUTE SCRIPT INIT_GLOSSARY WITH "
        f"(glossary_db_alias=initial, glossary_table={table}, name_col=term, def_col=definition)\n"
    )


_REPLACEMENT = (
    "execsql: COPY ... TO REPLACEMENT fails on SQL Server when the target table does not exist yet "
    "(ss_glossary copies to REPLACEMENT gls_newentries2)"
)


def _glossary(target, body: str, tmp_path) -> list[dict[str, str]]:
    result = target.run("glossary", body + "-- !x! EXPORT glossary TO glossary.csv AS CSV\n", tmp_path=tmp_path)
    assert result.success, result.errors
    return read_csv(tmp_path / "glossary.csv")


def test_a_list_of_terms_takes_their_definitions_from_the_master(target, tmp_path):
    known_bug(target, "sqlserver", _REPLACEMENT)
    table = _master(target)
    rows = _glossary(
        target,
        _init(table) + '-- !x! EXECUTE SCRIPT ADD_GLOSSARY_LIST WITH (column_list="site_id, sample_date")\n',
        tmp_path,
    )
    assert rows == [
        {"term": "sample_date", "definition": "Date the sample was collected"},
        {"term": "site_id", "definition": "Site identifier"},
    ]


_MYSQL_CAST = "md_glossary ADD_GLOSSARY_ITEM casts to varchar(255); MySQL's CAST takes CHAR, not VARCHAR"


def test_an_item_can_be_added_with_its_own_definition(target, tmp_path):
    known_bug(target, "mysql", _MYSQL_CAST)
    table = _master(target)
    rows = _glossary(
        target,
        _init(table) + '-- !x! EXECUTE SCRIPT ADD_GLOSSARY_ITEM WITH (item=lab, definition="Laboratory name")\n',
        tmp_path,
    )
    assert rows == [{"term": "lab", "definition": "Laboratory name"}]


def test_a_term_added_twice_appears_once(target, tmp_path):
    known_bug(target, "sqlserver", _REPLACEMENT)
    known_bug(target, "mysql", _MYSQL_CAST)
    table = _master(target)
    rows = _glossary(
        target,
        _init(table)
        + '-- !x! EXECUTE SCRIPT ADD_GLOSSARY_LIST WITH (column_list="site_id")\n'
        + '-- !x! EXECUTE SCRIPT ADD_GLOSSARY_LIST WITH (column_list="site_id, result")\n'
        + '-- !x! EXECUTE SCRIPT ADD_GLOSSARY_ITEM WITH (item=result, definition="Some other text")\n',
        tmp_path,
    )
    assert rows == [
        {"term": "result", "definition": "Measured value"},
        {"term": "site_id", "definition": "Site identifier"},
    ]


def test_a_table_adds_every_column_it_has(target, tmp_path):
    known_bug(target, "sqlserver", _REPLACEMENT)
    table = _master(target)
    data = target.table(target.base, "samples")
    target.execute(f"create table {data} (site_id varchar(10), sample_date date, result float)")
    if target.server.prefix == "md":
        add_table = "-- !x! EXECUTE SCRIPT ADD_GLOSSARY_TABLE WITH (table=samples)\n"
    else:
        add_table = f"-- !x! EXECUTE SCRIPT ADD_GLOSSARY_TABLE WITH (schema={target.base}, table=samples)\n"
    rows = _glossary(target, _init(table) + add_table, tmp_path)
    assert [r["term"] for r in rows] == ["result", "sample_date", "site_id"]
