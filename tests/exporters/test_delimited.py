"""
Integration tests for execsql.exporters.delimited.

Covers:
  - LineDelimiter.delimited()
  - DelimitedWriter.write / writerow / writerows
  - CsvWriter.writerow / writerows / close
  - write_delimited_file() for all supported format strings
  - CsvFile reading, column_headers, and reader()
"""

from __future__ import annotations

import io
import os

import pytest

from execsql.exporters.delimited import (
    LineDelimiter,
    DelimitedWriter,
    CsvWriter,
    write_delimited_file,
    CsvFile,
)


# ---------------------------------------------------------------------------
# Extra conf attributes required by CsvFile._colhdrs
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def csv_conf(minimal_conf):
    minimal_conf.del_empty_cols = False
    minimal_conf.create_col_hdrs = False
    minimal_conf.clean_col_hdrs = False
    minimal_conf.trim_col_hdrs = "none"
    minimal_conf.fold_col_hdrs = "no"
    minimal_conf.dedup_col_hdrs = False
    minimal_conf.import_encoding = "utf-8"
    minimal_conf.quote_all_text = False
    minimal_conf.scan_lines = 50
    yield minimal_conf


# ===========================================================================
# LineDelimiter
# ===========================================================================


class TestLineDelimiter:
    def test_csv_joins_with_comma(self):
        ld = LineDelimiter(",", '"', None)
        result = ld.delimited(["a", "b", "c"], add_newline=False)
        assert result == "a,b,c"

    def test_adds_newline_by_default(self):
        ld = LineDelimiter(",", None, None)
        result = ld.delimited(["x"])
        assert result.endswith("\n")

    def test_no_newline_when_disabled(self):
        ld = LineDelimiter(",", None, None)
        result = ld.delimited(["x"], add_newline=False)
        assert not result.endswith("\n")

    def test_none_values_become_empty_string(self):
        ld = LineDelimiter(",", None, None)
        result = ld.delimited([None, "a"], add_newline=False)
        assert result == ",a"

    def test_quote_char_applied_to_strings_with_delimiter(self):
        ld = LineDelimiter(",", '"', None)
        # String containing the delimiter should be quoted
        result = ld.delimited(["a,b"], add_newline=False)
        assert result == '"a,b"'

    def test_quote_char_applied_when_quote_all_text(self, minimal_conf):
        minimal_conf.quote_all_text = True
        ld = LineDelimiter(",", '"', None)
        result = ld.delimited(["hello"], add_newline=False)
        assert result == '"hello"'

    def test_quote_doubled_when_quote_in_value(self):
        ld = LineDelimiter(",", '"', None)
        result = ld.delimited(['say "hi"'], add_newline=False)
        assert '""' in result

    def test_escape_char_used_instead_of_doubled_quote(self):
        ld = LineDelimiter(",", '"', "\\")
        result = ld.delimited(['say "hi"'], add_newline=False)
        assert '\\"' in result

    def test_no_quotechar_no_escaping(self):
        ld = LineDelimiter("\t", None, None)
        result = ld.delimited(["a", "b"], add_newline=False)
        assert result == "a\tb"

    def test_tab_delimiter(self):
        ld = LineDelimiter("\t", None, None)
        result = ld.delimited(["x", "y", "z"], add_newline=False)
        assert result == "x\ty\tz"

    def test_integer_values_converted_to_str(self):
        ld = LineDelimiter(",", None, None)
        result = ld.delimited([1, 2, 3], add_newline=False)
        assert result == "1,2,3"

    def test_string_with_newline_is_quoted(self):
        ld = LineDelimiter(",", '"', None)
        result = ld.delimited(["line\nbreak"], add_newline=False)
        assert result.startswith('"')


# ===========================================================================
# DelimitedWriter
# ===========================================================================


class TestDelimitedWriter:
    def test_write_passes_through(self):
        buf = io.StringIO()
        dw = DelimitedWriter(buf, ",", None, None)
        dw.write("hello\n")
        assert buf.getvalue() == "hello\n"

    def test_writerow_produces_delimited_line(self):
        buf = io.StringIO()
        dw = DelimitedWriter(buf, ",", None, None)
        dw.writerow(["a", "b", "c"])
        assert buf.getvalue() == "a,b,c\n"

    def test_writerows_writes_multiple_rows(self):
        buf = io.StringIO()
        dw = DelimitedWriter(buf, ",", None, None)
        dw.writerows([["a", "b"], ["c", "d"]])
        lines = buf.getvalue().splitlines()
        assert lines == ["a,b", "c,d"]


# ===========================================================================
# CsvWriter
# ===========================================================================


class TestCsvWriter:
    def test_writerow_to_file(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.csv")
        w = CsvWriter(out, "utf-8", ",", '"', None)
        w.writerow(["id", "name"])
        w.writerow([1, "Alice"])
        w.close()
        text = (tmp_path / "out.csv").read_text()
        assert "id,name" in text
        assert "1,Alice" in text

    def test_writerows_to_file(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.csv")
        w = CsvWriter(out, "utf-8", "\t", None, None)
        w.writerows([["a", "b"], ["c", "d"]])
        w.close()
        lines = (tmp_path / "out.csv").read_text().splitlines()
        assert lines == ["a\tb", "c\td"]

    def test_append_mode_grows_file(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.csv")
        w1 = CsvWriter(out, "utf-8", ",", None, None)
        w1.writerow(["a"])
        w1.close()
        first_size = os.path.getsize(out)
        w2 = CsvWriter(out, "utf-8", ",", None, None, append=True)
        w2.writerow(["b"])
        w2.close()
        assert os.path.getsize(out) > first_size


# ===========================================================================
# write_delimited_file
# ===========================================================================


class TestWriteDelimitedFile:
    def _write(self, fmt, headers, rows, tmp_path, **kwargs):
        out = str(tmp_path / f"out.{fmt}")
        write_delimited_file(out, fmt, headers, iter(rows), **kwargs)
        return (tmp_path / f"out.{fmt}").read_text()

    def test_csv_format(self, noop_filewriter_close, tmp_path):
        text = self._write("csv", ["a", "b"], [[1, 2], [3, 4]], tmp_path)
        assert "a,b" in text
        assert "1,2" in text

    def test_tsv_format(self, noop_filewriter_close, tmp_path):
        text = self._write("tsv", ["x", "y"], [["p", "q"]], tmp_path)
        assert "x\ty" in text
        assert "p\tq" in text

    def test_tab_format(self, noop_filewriter_close, tmp_path):
        text = self._write("tab", ["x"], [["v"]], tmp_path)
        assert "x" in text

    def test_tabq_format(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.tabq")
        write_delimited_file(out, "tabq", ["c1"], iter([["val"]]))
        text = (tmp_path / "out.tabq").read_text()
        assert "c1" in text

    def test_tsvq_format(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.tsvq")
        write_delimited_file(out, "tsvq", ["c1"], iter([["val"]]))
        text = (tmp_path / "out.tsvq").read_text()
        assert "c1" in text

    def test_unitsep_format(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.us")
        write_delimited_file(out, "us", ["a", "b"], iter([[1, 2]]))
        text = (tmp_path / "out.us").read_text()
        assert chr(31) in text  # unit separator

    def test_plain_format_no_header(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.plain")
        write_delimited_file(out, "plain", ["hdr"], iter([["value"]]))
        text = (tmp_path / "out.plain").read_text()
        # plain format skips the header line
        assert "hdr" not in text
        assert "value" in text

    def test_latex_format(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.latex")
        write_delimited_file(out, "latex", ["a", "b"], iter([[1, 2]]))
        text = (tmp_path / "out.latex").read_text()
        assert "&" in text  # LaTeX column separator

    def test_append_mode_skips_header(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.csv")
        write_delimited_file(out, "csv", ["col"], iter([[1]]))
        write_delimited_file(out, "csv", ["col"], iter([[2]]), append=True)
        text = (tmp_path / "out.csv").read_text()
        # Header appears only once in append mode
        assert text.count("col") == 1

    def test_empty_rowsource_writes_only_header(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.csv")
        write_delimited_file(out, "csv", ["a", "b"], iter([]))
        text = (tmp_path / "out.csv").read_text()
        assert "a,b" in text
        assert text.strip() == "a,b"


# ===========================================================================
# CsvFile
# ===========================================================================


class TestCsvFile:
    @pytest.fixture
    def simple_csv(self, tmp_path):
        """Write a minimal CSV and return its path."""
        p = tmp_path / "data.csv"
        p.write_text("id,name\n1,Alice\n2,Bob\n", encoding="utf-8")
        return str(p)

    @pytest.fixture
    def tab_csv(self, tmp_path):
        p = tmp_path / "data.tsv"
        p.write_text("id\tname\n1\tAlice\n2\tBob\n", encoding="utf-8")
        return str(p)

    def test_repr(self, simple_csv):
        cf = CsvFile(simple_csv, "utf-8")
        assert "CsvFile(" in repr(cf)
        # Use repr(simple_csv) because __repr__ uses !r, which escapes backslashes on Windows.
        assert repr(simple_csv) in repr(cf)

    def test_lineformat_sets_attributes(self, simple_csv):
        cf = CsvFile(simple_csv, "utf-8")
        cf.lineformat(",", '"', None)
        assert cf.delimiter == ","
        assert cf.quotechar == '"'
        assert cf.lineformat_set is True

    def test_column_headers_auto_detected(self, simple_csv):
        cf = CsvFile(simple_csv, "utf-8")
        hdrs = cf.column_headers()
        assert hdrs == ["id", "name"]

    def test_reader_yields_rows(self, simple_csv):
        cf = CsvFile(simple_csv, "utf-8")
        cf.column_headers()  # triggers format evaluation
        rows = list(cf.reader())
        # First yielded element is the header row; data follows
        assert len(rows) >= 2

    def test_tab_delimited_detection(self, tab_csv):
        cf = CsvFile(tab_csv, "utf-8")
        hdrs = cf.column_headers()
        assert hdrs == ["id", "name"]

    def test_junk_header_lines_skipped(self, tmp_path):
        p = tmp_path / "junk.csv"
        p.write_text("# comment\nid,val\n1,x\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8", junk_header_lines=1)
        hdrs = cf.column_headers()
        assert hdrs == ["id", "val"]

    def test_evaluate_column_types_populates_table_data(self, simple_csv):
        cf = CsvFile(simple_csv, "utf-8")
        cf.evaluate_column_types()
        assert cf.table_data is not None

    def test_data_table_def_returns_table(self, simple_csv):
        cf = CsvFile(simple_csv, "utf-8")
        td = cf.data_table_def()
        assert td is not None

    def test_writer_returns_csvwriter(self, tmp_path, noop_filewriter_close):
        p = tmp_path / "data.csv"
        p.write_text("id,name\n1,Alice\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        cf.column_headers()  # triggers format detection
        w = cf.writer()
        assert isinstance(w, CsvWriter)
        w.close()

    def test_openclean_skips_junk_lines(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("junk\nid,val\n1,x\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8", junk_header_lines=1)
        f = cf.openclean("rt")
        first_line = f.readline().strip()
        assert first_line == "id,val"
        f.close()

    def test_colhdrs_del_empty_cols(self, tmp_path, minimal_conf):
        minimal_conf.del_empty_cols = True
        p = tmp_path / "data.csv"
        p.write_text("id,,name\n1,x,Alice\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        hdrs = cf.column_headers()
        assert "" not in hdrs
        assert "id" in hdrs
        assert "name" in hdrs

    def test_colhdrs_create_col_hdrs(self, tmp_path, minimal_conf):
        minimal_conf.create_col_hdrs = True
        p = tmp_path / "data.csv"
        p.write_text("id,,name\n1,x,Alice\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        hdrs = cf.column_headers()
        assert "Col2" in hdrs

    def test_colhdrs_missing_headers_raises(self, tmp_path, minimal_conf):
        from execsql.exceptions import ErrInfo

        minimal_conf.del_empty_cols = False
        minimal_conf.create_col_hdrs = False
        p = tmp_path / "data.csv"
        p.write_text("id,,name\n1,x,Alice\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        with pytest.raises(ErrInfo):
            cf.column_headers()

    def test_reader_with_quoted_csv(self, tmp_path):
        p = tmp_path / "quoted.csv"
        p.write_text('id,name\n1,"Alice, Jr."\n', encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        cf.column_headers()
        rows = list(cf.reader())
        # rows includes header + data rows
        data_rows = [r for r in rows if r[0] != "id"]
        assert any("Alice" in str(r) for r in data_rows)

    def test_colhdrs_via_iterator(self, tmp_path, minimal_conf):
        # _colhdrs works with any iterator that yields lists of strings
        p = tmp_path / "data.csv"
        p.write_text("id,name\n1,Alice\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")

        def fake_reader():
            yield ["id", "name"]
            yield ["1", "Alice"]

        hdrs = cf._colhdrs(fake_reader())
        assert hdrs == ["id", "name"]


# ===========================================================================
# CsvLine (internal class)
# ===========================================================================


class TestCsvLine:
    """Tests for CsvFile.CsvLine via CsvFile instances."""

    def _make_line(self, text):
        """Instantiate a CsvLine from CsvFile's inner class."""
        return CsvFile.CsvLine(text)

    def test_str_includes_text(self):
        line = self._make_line("a,b,c")
        line.count_delim(",")
        s = str(line)
        assert "a,b,c" in s

    def test_count_delim_comma(self):
        line = self._make_line("a,b,c")
        line.count_delim(",")
        assert line.delim_count(",") == 2

    def test_count_delim_space(self):
        line = self._make_line("a  b  c")
        line.count_delim(" ")
        assert line.delim_count(" ") == 2

    def test_items_no_delim_no_quote(self):
        line = self._make_line("hello world")
        result = line.items(None, None)
        assert result == "hello world"

    def test_items_comma_no_quote(self):
        line = self._make_line("a,b,c")
        result = line.items(",", None)
        assert result == ["a", "b", "c"]

    def test_items_space_delim_collapses_spaces(self):
        line = self._make_line("a  b  c")
        result = line.items(" ", None)
        assert result == ["a", "b", "c"]

    def test_items_quoted_field_with_delimiter(self):
        # items() is a raw parser: surrounding quotes are preserved in the output
        line = self._make_line('"a,b",c')
        result = line.items(",", '"')
        assert len(result) == 2
        assert "a,b" in result[0]  # delimiter is inside the quoted field
        assert result[1] == "c"

    def test_items_doubled_quote_inside_quoted(self):
        line = self._make_line('"say ""hi""",end')
        result = line.items(",", '"')
        assert "say" in result[0]
        assert result[1] == "end"

    def test_well_quoted_no_quotes(self):
        line = self._make_line("abc")
        wq, uses_q, escaped = line._well_quoted("abc", '"')
        assert wq is True
        assert uses_q is False

    def test_well_quoted_properly_quoted(self):
        line = self._make_line('"abc"')
        wq, uses_q, escaped = line._well_quoted('"abc"', '"')
        assert wq is True
        assert uses_q is True

    def test_well_quoted_improperly_quoted(self):
        line = self._make_line('a"b')
        wq, uses_q, escaped = line._well_quoted('a"b', '"')
        assert wq is False
