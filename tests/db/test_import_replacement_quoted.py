"""``IMPORT TO REPLACEMENT`` / ``COPY ... TO REPLACEMENT`` replace a table whose name needs quoting."""

from __future__ import annotations

from execsql import run


def test_import_to_replacement_of_a_quoted_name(tmp_path):
    csv = tmp_path / "q.csv"
    csv.write_text("a,b\n1,2\n")
    db = tmp_path / "t.db"
    script = f'-- !x! IMPORT TO NEW "my tbl" FROM {csv}\n-- !x! IMPORT TO REPLACEMENT "my tbl" FROM {csv}\n'
    result = run(sql=script, dsn=f"sqlite:///{db}", new_db=True)
    assert result.success, result.errors

    import sqlite3

    con = sqlite3.connect(db)
    try:
        assert con.execute('select count(*) from "my tbl"').fetchone()[0] == 1
    finally:
        con.close()
