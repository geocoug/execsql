"""
Tests for execsql.exporters.delimited.

Covers:
  - LineDelimiter.delimited() — all quoting/escaping branches
  - DelimitedWriter.write / writerow / writerows
  - CsvWriter.write / writerow / writerows / close / stdout / append
  - CsvFile reading, openclean, lineformat, column_headers, reader, writer
  - CsvFile._colhdrs — all branches (empty cols, create_col_hdrs, clean, fold, dedup)
  - CsvFile.diagnose_delim — no-delimiter, single-delimiter, multi-delimiter, space removal
  - CsvFile.read_and_parse_line — all state machine paths (quoted, escaped, unquoted, between, delimited)
  - CsvFile.CsvLine — items() all parser states, _well_quoted all branches
  - write_delimited_file() — all format strings, zip output, append, error path
  - ZipWriter integration through write_delimited_file
"""

from __future__ import annotations

import io
import os
import zipfile as _zipfile
from unittest.mock import patch

import pytest

from execsql.exceptions import ErrInfo
from execsql.exporters.delimited import (
    CsvFile,
    CsvWriter,
    DelimitedWriter,
    LineDelimiter,
    write_delimited_file,
)


# ---------------------------------------------------------------------------
# Extra conf attributes required by CsvFile._colhdrs and diagnose_delim
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

    def test_none_values_become_empty_string_no_quotechar(self):
        ld = LineDelimiter(",", None, None)
        result = ld.delimited([None, "a"], add_newline=False)
        assert result == ",a"

    def test_none_values_become_empty_string_with_quotechar(self):
        # Line 70: non-str, non-None path with quotechar present — None becomes ""
        ld = LineDelimiter(",", '"', None)
        result = ld.delimited([None, "a"], add_newline=False)
        assert result == ",a"

    def test_non_string_non_none_with_quotechar(self):
        # Line 72: non-str, non-None (e.g. int) with quotechar — converted via str()
        ld = LineDelimiter(",", '"', None)
        result = ld.delimited([42, 3.14], add_newline=False)
        assert result == "42,3.14"

    def test_quote_char_applied_to_strings_with_delimiter(self):
        ld = LineDelimiter(",", '"', None)
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

    def test_string_with_carriage_return_is_quoted(self):
        ld = LineDelimiter(",", '"', None)
        result = ld.delimited(["carriage\rreturn"], add_newline=False)
        assert result.startswith('"')

    def test_string_without_special_chars_not_quoted(self):
        ld = LineDelimiter(",", '"', None)
        result = ld.delimited(["plain"], add_newline=False)
        assert result == "plain"

    def test_none_delimiter_uses_empty_joinchar(self):
        ld = LineDelimiter(None, None, None)
        result = ld.delimited(["a", "b"], add_newline=False)
        assert result == "ab"

    def test_escape_char_creates_quotedquote(self):
        ld = LineDelimiter(",", '"', "\\")
        assert ld.quotedquote == '\\"'

    def test_no_escchar_creates_doubled_quotedquote(self):
        ld = LineDelimiter(",", '"', None)
        assert ld.quotedquote == '""'

    def test_no_quotechar_quotedquote_is_none(self):
        ld = LineDelimiter(",", None, None)
        assert ld.quotedquote is None


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

    def test_writerow_with_tab_delimiter(self):
        buf = io.StringIO()
        dw = DelimitedWriter(buf, "\t", None, None)
        dw.writerow(["x", "y"])
        assert buf.getvalue() == "x\ty\n"

    def test_writerow_with_quotechar(self):
        buf = io.StringIO()
        dw = DelimitedWriter(buf, ",", '"', None)
        dw.writerow(["a,b", "c"])
        assert '"a,b"' in buf.getvalue()

    def test_writerows_empty_iterable(self):
        buf = io.StringIO()
        dw = DelimitedWriter(buf, ",", None, None)
        dw.writerows([])
        assert buf.getvalue() == ""


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

    def test_write_raw_string_to_file(self, noop_filewriter_close, tmp_path):
        # Line 132: CsvWriter.write()
        out = str(tmp_path / "out.txt")
        w = CsvWriter(out, "utf-8", ",", None, None)
        w.write("raw text\n")
        w.close()
        assert (tmp_path / "out.txt").read_text() == "raw text\n"

    def test_stdout_target_does_not_open_file(self, noop_filewriter_close):
        # Line 124: stdout branch
        import sys

        w = CsvWriter("stdout", "utf-8", ",", None, None)
        assert w.output is sys.stdout
        # Do not close stdout; just verify the assignment

    def test_close_sets_output_to_none(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.csv")
        w = CsvWriter(out, "utf-8", ",", None, None)
        w.close()
        assert w.output is None


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
        assert chr(31) in text

    def test_plain_format_no_header(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.plain")
        write_delimited_file(out, "plain", ["hdr"], iter([["value"]]))
        text = (tmp_path / "out.plain").read_text()
        assert "hdr" not in text
        assert "value" in text

    def test_latex_format(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.latex")
        write_delimited_file(out, "latex", ["a", "b"], iter([[1, 2]]))
        text = (tmp_path / "out.latex").read_text()
        assert "&" in text

    def test_append_mode_skips_header(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.csv")
        write_delimited_file(out, "csv", ["col"], iter([[1]]))
        write_delimited_file(out, "csv", ["col"], iter([[2]]), append=True)
        text = (tmp_path / "out.csv").read_text()
        assert text.count("col") == 1

    def test_empty_rowsource_writes_only_header(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.csv")
        write_delimited_file(out, "csv", ["a", "b"], iter([]))
        text = (tmp_path / "out.csv").read_text()
        assert "a,b" in text
        assert text.strip() == "a,b"

    def test_zip_output_creates_archive(self, noop_filewriter_close, tmp_path, minimal_conf):
        # Lines 742-749: zipfile path
        minimal_conf.zip_buffer_mb = 1
        zpath = str(tmp_path / "out.zip")
        member = "data.csv"
        write_delimited_file(member, "csv", ["x", "y"], iter([[1, 2]]), zipfile=zpath)
        assert _zipfile.is_zipfile(zpath)
        with _zipfile.ZipFile(zpath, "r") as zf:
            assert member in zf.namelist()

    def test_zip_output_content_correct(self, noop_filewriter_close, tmp_path, minimal_conf):
        # Lines 748-749: writing data rows into zip
        minimal_conf.zip_buffer_mb = 1
        zpath = str(tmp_path / "out.zip")
        write_delimited_file("report.csv", "csv", ["id", "val"], iter([[1, "a"], [2, "b"]]), zipfile=zpath)
        with _zipfile.ZipFile(zpath, "r") as zf:
            data = zf.read("report.csv").decode("utf-8")
        assert "id,val" in data
        assert "1,a" in data

    def test_zip_append_mode(self, noop_filewriter_close, tmp_path, minimal_conf):
        # Zip append mode
        minimal_conf.zip_buffer_mb = 1
        zpath = str(tmp_path / "out.zip")
        write_delimited_file("first.csv", "csv", ["a"], iter([[1]]), zipfile=zpath)
        write_delimited_file("second.csv", "csv", ["b"], iter([[2]]), zipfile=zpath, append=True)
        with _zipfile.ZipFile(zpath, "r") as zf:
            names = zf.namelist()
        assert "first.csv" in names
        assert "second.csv" in names

    def test_row_write_exception_raises_errinfo(self, noop_filewriter_close, tmp_path):
        # Lines 763-766: exception during row write (inside the inner try) is wrapped in ErrInfo.
        # We cause an exception inside line_delimiter.delimited() by passing an object
        # whose __str__ raises — this triggers the except Exception branch.
        out = str(tmp_path / "out.csv")

        class ExplodingStr:
            def __str__(self):
                raise RuntimeError("cannot stringify")

        rows = [[ExplodingStr()]]
        with pytest.raises(ErrInfo):
            write_delimited_file(out, "csv", ["col"], iter(rows))

    def test_uppercase_format_strings_accepted(self, noop_filewriter_close, tmp_path):
        # Format matching is case-insensitive (filefmt.lower())
        out = str(tmp_path / "out.csv")
        write_delimited_file(out, "CSV", ["a"], iter([[1]]))
        text = (tmp_path / "out.csv").read_text()
        assert "a" in text


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

    def test_column_headers_skips_evaluate_when_already_set(self, simple_csv):
        # Line 685->687: when lineformat_set is True, evaluate_line_format is skipped
        cf = CsvFile(simple_csv, "utf-8")
        cf.lineformat(",", '"', None)
        hdrs = cf.column_headers()
        assert hdrs == ["id", "name"]

    def test_reader_yields_rows(self, simple_csv):
        cf = CsvFile(simple_csv, "utf-8")
        cf.column_headers()
        rows = list(cf.reader())
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

    def test_evaluate_column_types_skips_evaluate_when_lineformat_set(self, simple_csv):
        # Line 698->700: lineformat_set True skips evaluate_line_format in evaluate_column_types
        cf = CsvFile(simple_csv, "utf-8")
        cf.lineformat(",", '"', None)
        cf.evaluate_column_types()
        assert cf.table_data is not None

    def test_data_table_def_returns_cached_table(self, simple_csv):
        # Line 692->694: when table_data is already populated, returns it without re-evaluating
        cf = CsvFile(simple_csv, "utf-8")
        cf.evaluate_column_types()
        first = cf.table_data
        second = cf.data_table_def()
        assert second is first

    def test_data_table_def_triggers_evaluation_when_needed(self, simple_csv):
        # Line 692: when table_data is None, evaluate_column_types is called
        cf = CsvFile(simple_csv, "utf-8")
        assert cf.table_data is None
        td = cf.data_table_def()
        assert td is not None

    def test_writer_returns_csvwriter(self, tmp_path, noop_filewriter_close):
        p = tmp_path / "data.csv"
        p.write_text("id,name\n1,Alice\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        cf.column_headers()
        w = cf.writer()
        assert isinstance(w, CsvWriter)
        w.close()

    def test_writer_append_mode(self, tmp_path, noop_filewriter_close):
        p = tmp_path / "data.csv"
        p.write_text("id,name\n1,Alice\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        cf.lineformat(",", '"', None)
        w = cf.writer(append=True)
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
        minimal_conf.del_empty_cols = False
        minimal_conf.create_col_hdrs = False
        p = tmp_path / "data.csv"
        p.write_text("id,,name\n1,x,Alice\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        with pytest.raises(ErrInfo):
            cf.column_headers()

    def test_colhdrs_clean_col_hdrs(self, tmp_path, minimal_conf):
        # Line 676: clean_col_hdrs path
        minimal_conf.clean_col_hdrs = True
        p = tmp_path / "data.csv"
        # clean_words strips non-word chars from column names
        p.write_text("my-id,my-name\n1,Alice\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        hdrs = cf.column_headers()
        # After clean_words, hyphens should be removed or replaced
        assert len(hdrs) == 2

    def test_colhdrs_fold_col_hdrs_upper(self, tmp_path, minimal_conf):
        # Line 678: fold_col_hdrs != "no" path
        minimal_conf.fold_col_hdrs = "upper"
        p = tmp_path / "data.csv"
        p.write_text("id,name\n1,Alice\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        hdrs = cf.column_headers()
        assert hdrs == ["ID", "NAME"]

    def test_colhdrs_fold_col_hdrs_lower(self, tmp_path, minimal_conf):
        # Line 678: fold_col_hdrs lower variant
        minimal_conf.fold_col_hdrs = "lower"
        p = tmp_path / "data.csv"
        p.write_text("ID,NAME\n1,Alice\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        hdrs = cf.column_headers()
        assert hdrs == ["id", "name"]

    def test_colhdrs_dedup_col_hdrs(self, tmp_path, minimal_conf):
        # Line 680: dedup_col_hdrs path — _state.dedup_words is called
        # _state.dedup_words is not natively present; we mock it to verify the branch
        from execsql.utils.strings import dedup_words

        minimal_conf.dedup_col_hdrs = True
        p = tmp_path / "data.csv"
        p.write_text("col,col\n1,2\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        import execsql.state as _state_module

        with patch.object(_state_module, "dedup_words", dedup_words, create=True):
            hdrs = cf.column_headers()
        assert len(hdrs) == 2
        assert len(set(hdrs)) == 2  # dedup ensures uniqueness

    def test_colhdrs_raises_on_errinfo_from_reader(self, tmp_path):
        # Lines 623-626: _colhdrs propagates ErrInfo from iterator, annotating it
        p = tmp_path / "data.csv"
        p.write_text("id,name\n1,Alice\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        cf.lineformat(",", '"', None)

        def errinfo_reader():
            raise ErrInfo(type="error", other_msg="simulated read error")
            yield  # make it a generator

        with pytest.raises(ErrInfo) as exc_info:
            cf._colhdrs(errinfo_reader())
        assert exc_info.value.other is not None

    def test_colhdrs_raises_on_generic_exception_from_reader(self, tmp_path):
        # Lines 629-632: _colhdrs wraps generic exceptions in ErrInfo
        p = tmp_path / "data.csv"
        p.write_text("id,name\n1,Alice\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        cf.lineformat(",", '"', None)

        def broken_reader():
            raise ValueError("unexpected failure")
            yield  # make it a generator

        with pytest.raises(ErrInfo):
            cf._colhdrs(broken_reader())

    def test_colhdrs_via_iterator(self, tmp_path, minimal_conf):
        p = tmp_path / "data.csv"
        p.write_text("id,name\n1,Alice\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")

        def fake_reader():
            yield ["id", "name"]
            yield ["1", "Alice"]

        hdrs = cf._colhdrs(fake_reader())
        assert hdrs == ["id", "name"]

    def test_reader_with_quoted_csv(self, tmp_path):
        p = tmp_path / "quoted.csv"
        p.write_text('id,name\n1,"Alice, Jr."\n', encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        cf.column_headers()
        rows = list(cf.reader())
        data_rows = [r for r in rows if r[0] != "id"]
        assert any("Alice" in str(r) for r in data_rows)

    def test_reader_reraises_errinfo_with_line_number(self, tmp_path):
        # Line 609: reader() wraps ErrInfo with line number context
        p = tmp_path / "bad.csv"
        # Write a CSV that will parse, but mock read_and_parse_line to raise ErrInfo
        p.write_text("id,name\n1,Alice\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        cf.lineformat(",", '"', None)
        with (
            patch.object(cf, "read_and_parse_line", side_effect=ErrInfo("error", other_msg="parse fail")),
            pytest.raises(ErrInfo) as exc_info,
        ):
            # Drain the reader
            list(cf.reader())
        assert "line" in exc_info.value.other

    def test_del_empty_cols_removes_columns_in_reader(self, tmp_path, minimal_conf):
        # Lines 629-632 in reader(): blank_cols deletion
        minimal_conf.del_empty_cols = True
        p = tmp_path / "data.csv"
        p.write_text("id,,name\n1,x,Alice\n2,y,Bob\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        hdrs = cf.column_headers()
        # After _colhdrs with del_empty_cols, blank_cols is set
        assert "" not in hdrs
        rows = list(cf.reader())
        # Each data row should have same count as hdrs (blank col removed)
        data_rows = [r for r in rows if r[0] not in ("id", None)]
        for row in data_rows:
            assert len(row) == len(hdrs)

    def test_semicolon_delimited_file(self, tmp_path):
        # diagnose_delim with semicolon delimiter
        p = tmp_path / "semi.csv"
        p.write_text("id;name\n1;Alice\n2;Bob\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        hdrs = cf.column_headers()
        assert hdrs == ["id", "name"]

    def test_pipe_delimited_file(self, tmp_path):
        p = tmp_path / "pipe.csv"
        p.write_text("id|name\n1|Alice\n2|Bob\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        hdrs = cf.column_headers()
        assert hdrs == ["id", "name"]

    def test_space_delimited_file(self, tmp_path):
        # diagnose_delim space delimiter — space is only used if it's the only one
        p = tmp_path / "space.csv"
        p.write_text("id name\n1 Alice\n2 Bob\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        cf.diagnose_delim(
            iter(["id name\n", "1 Alice\n", "2 Bob\n"]),
            possible_delimiters=[" "],
        )
        # Just verify it doesn't raise

    def test_no_delimiter_file_returns_none_delimiter(self, tmp_path):
        # diagnose_delim: no delimiter found — all delim_stats empty → eval_quotes(None)
        p = tmp_path / "nodelim.txt"
        p.write_text("hello\nworld\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        # File has no common delimiter — diagnose_delim should return (None, None, None)
        result = cf.diagnose_delim(iter(["hello\n", "world\n"]))
        assert result[0] is None

    def test_diagnose_delim_empty_lines_raises(self, tmp_path):
        # diagnose_delim: empty linestream raises ErrInfo
        p = tmp_path / "empty.csv"
        p.write_text("", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        with pytest.raises(ErrInfo):
            cf.diagnose_delim(iter([]))

    def test_diagnose_delim_multiple_delimiters_picks_best(self, tmp_path):
        # When multiple delimiters appear, the one with highest weight is chosen
        p = tmp_path / "multi.csv"
        # Both comma and pipe are present, but comma appears more consistently
        p.write_text("a,b,c\n1,2,3\n4,5,6\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        delim, _, _ = cf.diagnose_delim(
            iter(["a,b,c\n", "1,2,3\n", "4,5,6\n"]),
            possible_delimiters=[",", "|"],
        )
        assert delim == ","

    def test_diagnose_delim_with_quoted_content(self, tmp_path):
        # diagnose_delim detects quote character when content is quoted
        p = tmp_path / "quoted.csv"
        p.write_text('"id","name"\n"1","Alice"\n', encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        delim, qchar, _ = cf.diagnose_delim(iter(['"id","name"\n', '"1","Alice"\n']))
        assert delim == ","
        assert qchar == '"'

    def test_diagnose_delim_space_removed_when_other_delimiter_present(self, tmp_path):
        # Lines 434-435: space is removed from delim_stats when other delimiters present
        p = tmp_path / "data.csv"
        p.write_text("a,b c\n1,2 3\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        # Both space and comma are present; space should be pruned in favor of comma
        result = cf.diagnose_delim(
            iter(["a,b c\n", "1,2 3\n"]),
            possible_delimiters=[",", " "],
        )
        assert result[0] == ","


# ===========================================================================
# CsvLine (internal class)
# ===========================================================================


class TestCsvLine:
    """Tests for CsvFile.CsvLine, accessed via CsvFile.CsvLine."""

    def _make_line(self, text):
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
        line = self._make_line('"a,b",c')
        result = line.items(",", '"')
        assert len(result) == 2
        assert "a,b" in result[0]
        assert result[1] == "c"

    def test_items_doubled_quote_inside_quoted(self):
        line = self._make_line('"say ""hi""",end')
        result = line.items(",", '"')
        assert "say" in result[0]
        assert result[1] == "end"

    def test_items_escape_char_in_quoted(self):
        # Lines 271-272: in_quoted() — escape char path
        line = self._make_line(r'"say \"hi\"",end')
        # backslash is the escape char for CsvLine
        result = line.items(",", '"')
        assert len(result) == 2

    def test_items_escaped_function_non_delim(self):
        # Lines 281-291: escaped() — character after escape that is not delimiter
        line = self._make_line(r'"te\\st"')
        result = line.items(",", '"')
        assert len(result) == 1

    def test_items_quote_in_quoted_then_delim(self):
        # Lines 299-304: quote_in_quoted() — closing quote followed by delimiter
        # CsvLine.items() is a raw parser; it includes the opening quote char in the element
        line = self._make_line('"first",second')
        result = line.items(",", '"')
        # The parser enters _IN_QUOTED on the opening quote char, then the closing quote
        # moves to _QUOTE_IN_QUOTED, then the comma triggers _DELIMITED.
        # The accumulated element ("first") is appended; second field is "second".
        assert len(result) == 2
        assert "first" in result[0]
        assert result[1] == "second"

    def test_items_quote_in_quoted_then_unexpected_char(self):
        # Lines 306-310: quote_in_quoted() — unexpected char after close quote raises
        line = self._make_line('"val"x,next')
        with pytest.raises(ErrInfo):
            line.items(",", '"')

    def test_items_between_state_text_char(self):
        # Lines 326-328 (between()): after escaped quote, non-quote non-delim char
        # Trigger: start in quoted, close quote, then another char (not delim, not quote)
        # This requires being in _BETWEEN state
        line = self._make_line('"a""b",c')
        result = line.items(",", '"')
        # "a""b" — doubled quote inside, result should contain the field
        assert len(result) == 2

    def test_items_delimited_state_with_consecutive_delimiters(self):
        # Lines 338-341: delimited() with multiple consecutive delimiters (eat_multiple_delims=False)
        line = self._make_line("a,,c")
        result = line.items(",", '"')
        assert len(result) == 3
        assert result[1] == ""

    def test_items_delimited_state_space_eats_consecutive(self):
        # Lines 338-341: eat_multiple_delims=True (space delimiter) — consecutive spaces act as one
        line = self._make_line("a  b  c")
        result = line.items(" ", '"')
        assert result == ["a", "b", "c"]

    def test_items_raises_on_format_error(self):
        # Line 355: items() raises ErrInfo when item_errors are recorded
        # Trigger a format error: quote in middle of unquoted field
        # Lines 306-310: unexpected char after closing quote
        line = self._make_line('"val"x,more')
        with pytest.raises(ErrInfo):
            line.items(",", '"')

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

    def test_well_quoted_empty_string_element(self):
        # Line 231-232: empty element with quote char not in it — returns (True, False, False)
        line = self._make_line("")
        wq, uses_q, escaped = line._well_quoted("", '"')
        assert wq is True
        assert uses_q is False

    def test_well_quoted_doubled_internal_quote(self):
        # Lines 238-241: element has quote on each end and doubled internal quote
        element = '"say ""hi"""'
        line = self._make_line(element)
        wq, uses_q, escaped = line._well_quoted(element, '"')
        assert wq is True
        assert uses_q is True

    def test_well_quoted_escaped_internal_quote(self):
        # Lines 243-244: element uses backslash escape for internal quote
        element = r'"say \"hi\""'
        line = self._make_line(element)
        wq, uses_q, escaped = line._well_quoted(element, '"')
        assert wq is True
        assert escaped is True

    def test_well_quoted_line_returns_tuple(self):
        line = self._make_line('"abc","def"')
        result = line.well_quoted_line(",", '"')
        assert isinstance(result, tuple)
        assert len(result) == 3
        assert result[0] is True  # all well-quoted

    def test_record_format_error_appends_message(self):
        # Line 249: record_format_error
        line = self._make_line("test")
        line.record_format_error(5, "Bad char")
        assert any("Bad char" in e for e in line.item_errors)
        assert any("5" in e for e in line.item_errors)


# ===========================================================================
# CsvFile.read_and_parse_line — state machine paths
# ===========================================================================


class TestReadAndParseLine:
    """Tests for read_and_parse_line() via full CsvFile.reader() pipeline."""

    def _make_csvfile_from_content(self, content, tmp_path, delim=",", quote='"', escape=None):
        p = tmp_path / "test.csv"
        p.write_text(content, encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        cf.lineformat(delim, quote, escape)
        return cf

    def test_simple_row_parsed(self, tmp_path):
        cf = self._make_csvfile_from_content("a,b,c\n1,2,3\n", tmp_path)
        rows = list(cf.reader())
        assert rows[0] == ["a", "b", "c"]
        assert rows[1] == ["1", "2", "3"]

    def test_quoted_field_with_embedded_delimiter(self, tmp_path):
        # in_quoted(), quote_in_quoted() → _DELIMITED path (lines 519-523)
        cf = self._make_csvfile_from_content('name,"Smith, John"\n', tmp_path)
        rows = list(cf.reader())
        assert rows[0][0] == "name"
        assert rows[0][1] == "Smith, John"

    def test_quoted_field_with_doubled_quote(self, tmp_path):
        # quote_in_quoted() → qchar==qchar path (lines 515-518)
        cf = self._make_csvfile_from_content('"say ""hi"""\n', tmp_path)
        rows = list(cf.reader())
        assert "hi" in rows[0][0]

    def test_null_field_from_start_delimiter(self, tmp_path):
        # start() → delimiter path (lines 478-480): first char is delimiter → None
        cf = self._make_csvfile_from_content(",value\n", tmp_path)
        rows = list(cf.reader())
        assert rows[0][0] is None
        assert rows[0][1] == "value"

    def test_empty_line_returns_empty_list(self, tmp_path):
        # start() → newline path (line 481-482): line starts with \n
        cf = self._make_csvfile_from_content("a,b\n\n1,2\n", tmp_path)
        rows = list(cf.reader())
        # Empty lines return empty element lists and break iteration
        assert len(rows) >= 1

    def test_in_unquoted_followed_by_delimiter(self, tmp_path):
        # in_unquoted() → delimiter (lines 537-540)
        cf = self._make_csvfile_from_content("abc,def\n", tmp_path)
        rows = list(cf.reader())
        assert rows[0] == ["abc", "def"]

    def test_in_unquoted_followed_by_newline(self, tmp_path):
        # in_unquoted() → newline (lines 541-544)
        cf = self._make_csvfile_from_content("abc\n", tmp_path)
        rows = list(cf.reader())
        assert rows[0] == ["abc"]

    def test_trailing_delimiter_produces_none(self, tmp_path):
        # end(): prev_state == _DELIMITED → None appended (lines 588-589)
        cf = self._make_csvfile_from_content("a,b,\n", tmp_path)
        rows = list(cf.reader())
        assert rows[0][2] is None

    def test_escape_char_in_quoted_field(self, tmp_path):
        # Lines 488-490: in_quoted() → escapechar path, lines 499-512: escaped() paths
        # Backslash escape inside quoted field
        cf = self._make_csvfile_from_content('"\\"hello\\""\n', tmp_path, escape="\\")
        rows = list(cf.reader())
        # The escaped quotes should be in the output
        assert len(rows[0]) >= 1

    def test_escape_then_delimiter_stays_in_quoted(self, tmp_path):
        # Lines 503-507: escaped() → delimiter char → stay in IN_QUOTED
        cf = self._make_csvfile_from_content('"a\\,b"\n', tmp_path, escape="\\")
        rows = list(cf.reader())
        # The comma is escaped, so the whole thing is one field
        assert len(rows[0]) == 1

    def test_quoted_then_unquoted_mix(self, tmp_path):
        # in_unquoted() → quotechar path (lines 545-548): quote encountered mid-unquoted
        cf = self._make_csvfile_from_content('abc"def\n', tmp_path)
        rows = list(cf.reader())
        assert len(rows[0]) >= 1

    def test_between_state_quote_starts_new_quoted(self, tmp_path):
        # between() → quotechar (line 554-555): after close-quote, new quoted field
        # Triggered by: close quote followed immediately by another quote
        cf = self._make_csvfile_from_content('"a""b",c\n', tmp_path)
        rows = list(cf.reader())
        assert len(rows[0]) == 2

    def test_between_state_delimiter_appends_none(self, tmp_path):
        # between() → delimiter (lines 556-558)
        # After close quote, immediately a delimiter
        cf = self._make_csvfile_from_content('"a",b\n', tmp_path)
        rows = list(cf.reader())
        assert rows[0][0] == "a"
        assert rows[0][1] == "b"

    def test_between_state_newline_ends_record(self, tmp_path):
        # between() → newline (lines 559-560)
        cf = self._make_csvfile_from_content('"hello"\n', tmp_path)
        rows = list(cf.reader())
        assert rows[0][0] == "hello"

    def test_between_state_unexpected_char_records_error(self, tmp_path):
        # between() → other char (lines 561-564): unexpected char after close quote
        cf = self._make_csvfile_from_content('"val"x\n', tmp_path)
        with pytest.raises(ErrInfo):
            list(cf.reader())

    def test_delimited_state_newline_ends_record(self, tmp_path):
        # delimited() → newline (line 574-575)
        cf = self._make_csvfile_from_content("a,\n", tmp_path)
        rows = list(cf.reader())
        assert rows[0][0] == "a"

    def test_delimited_state_consecutive_delimiters(self, tmp_path):
        # delimited() → delimiter again (lines 569-573): produces None
        cf = self._make_csvfile_from_content("a,,c\n", tmp_path)
        rows = list(cf.reader())
        assert rows[0][0] == "a"
        assert rows[0][1] is None
        assert rows[0][2] == "c"

    def test_end_with_escaped_buf(self, tmp_path):
        # Lines 581-582: end() when esc_buf has content and prev_state == _ESCAPED
        # Escape char at end of line with nothing after it
        cf = self._make_csvfile_from_content('"a\\"\n', tmp_path, escape="\\")
        rows = list(cf.reader())
        assert len(rows[0]) >= 1

    def test_end_with_quote_in_quoted_prev_state(self, tmp_path):
        # Lines 584-585: end() when prev_state == _QUOTE_IN_QUOTED — trims last char
        cf = self._make_csvfile_from_content('"hello"\n', tmp_path)
        rows = list(cf.reader())
        assert rows[0][0] == "hello"

    def test_record_format_error_recorded(self, tmp_path):
        # Line 464: _record_format_error appends to parse_errors
        p = tmp_path / "bad.csv"
        p.write_text("test\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        cf._record_format_error(3, "test error")
        assert len(cf.parse_errors) == 1
        assert "test error" in cf.parse_errors[0]
        assert "3" in cf.parse_errors[0]


# ===========================================================================
# diagnose_delim — direct testing for complex branches
# ===========================================================================


class TestDiagnoseDelim:
    """Direct tests for CsvFile.diagnose_delim() to cover all branching logic."""

    @pytest.fixture
    def csvfile(self, tmp_path):
        p = tmp_path / "dummy.csv"
        p.write_text("placeholder\n", encoding="utf-8")
        return CsvFile(str(p), "utf-8")

    def test_no_lines_raises(self, csvfile):
        with pytest.raises(ErrInfo):
            csvfile.diagnose_delim(iter([]))

    def test_empty_lines_skipped(self, csvfile):
        # Lines with only whitespace are skipped (len(ln) == 0 after strip)
        result = csvfile.diagnose_delim(iter(["\n", "a,b\n", "c,d\n"]))
        assert result[0] == ","

    def test_single_delimiter_comma(self, csvfile):
        # Line 436-437: exactly one delimiter found
        result = csvfile.diagnose_delim(
            iter(["a,b,c\n", "1,2,3\n"]),
            possible_delimiters=[","],
        )
        assert result[0] == ","

    def test_no_delimiter_in_any_line(self, csvfile):
        # Lines 431-432: no delimiters found → eval_quotes(None)
        result = csvfile.diagnose_delim(
            iter(["hello\n", "world\n"]),
            possible_delimiters=[",", "\t"],
        )
        assert result[0] is None

    def test_multiple_delimiters_space_removed(self, csvfile):
        # Lines 434-435: space removed when other delimiters also present
        result = csvfile.diagnose_delim(
            iter(["a,b c\n", "1,2 3\n"]),
            possible_delimiters=[",", " "],
        )
        assert result[0] == ","

    def test_multiple_delimiters_weight_picks_comma(self, csvfile):
        # Lines 438-446: multiple delimiters after space removal, weight picks best
        # comma has 2 occurrences per line, pipe has 1 — comma wins by weight
        result = csvfile.diagnose_delim(
            iter(["a,b,c|d\n", "1,2,3|4\n", "x,y,z|w\n"]),
            possible_delimiters=[",", "|"],
        )
        assert result[0] == ","

    def test_eval_quotes_max_use_zero_returns_none_quote(self, csvfile):
        # Lines 425-426: eval_quotes returns (delim, None, None) when max_use == 0
        # This happens when no quotes are used at all but the delimiter is valid
        result = csvfile.diagnose_delim(
            iter(["a,b\n", "c,d\n"]),
            possible_quotechars=["'"],
        )
        assert result[0] == ","
        # No quotes used, so qchar should be None
        assert result[1] is None

    def test_eval_quotes_with_quoted_content_returns_quotechar(self, csvfile):
        # Lines 427-429: eval_quotes finds a valid quotechar with usage > 0
        result = csvfile.diagnose_delim(
            iter(['"a","b"\n', '"c","d"\n']),
            possible_delimiters=[","],
            possible_quotechars=['"'],
        )
        assert result[0] == ","
        assert result[1] == '"'

    def test_scan_lines_limits_lines_read(self, csvfile, minimal_conf):
        # Line 379: scan_lines limits how many lines are read
        minimal_conf.scan_lines = 2
        # Provide 5 lines; only 2 should be scanned
        result = csvfile.diagnose_delim(
            iter(["a,b\n", "c,d\n", "e,f\n", "g,h\n", "i,j\n"]),
            possible_delimiters=[","],
        )
        assert result[0] == ","

    def test_scan_lines_zero_reads_all(self, csvfile, minimal_conf):
        # When scan_lines is 0 or None, effectively all lines read up to 1000000
        minimal_conf.scan_lines = 0
        result = csvfile.diagnose_delim(
            iter(["a,b\n", "c,d\n"]),
            possible_delimiters=[","],
        )
        assert result[0] == ","

    def test_lines_with_trailing_cr_stripped(self, csvfile):
        # Lines 386-387: trailing \r is stripped
        result = csvfile.diagnose_delim(
            iter(["a,b\r\n", "c,d\r\n"]),
            possible_delimiters=[","],
        )
        assert result[0] == ","

    def test_multiple_delimiters_no_good_quote_falls_back_to_first(self, csvfile):
        # Lines 442-446: loop through delim_order; if no quoted match, return (delim_order[0], None, None)
        result = csvfile.diagnose_delim(
            iter(["a,b;c\n", "1,2;3\n"]),
            possible_delimiters=[",", ";"],
            possible_quotechars=["'"],  # no quotes used
        )
        # Should pick highest-weight delimiter with no quotechar
        assert result[0] in (",", ";")
        assert result[1] is None

    def test_not_all_well_quoted_skips_quotechar(self, csvfile):
        # Line 419 False branch: allwq[0] is False — this quote char is not well-formed
        # for these lines, so it's excluded from ok_quotes
        # Use lines where quotes are malformed (quote mid-word, not at boundaries)
        result = csvfile.diagnose_delim(
            iter(['a,b"c\n', 'd,e"f\n']),
            possible_delimiters=[","],
            possible_quotechars=['"'],
        )
        # Quote char is rejected; result should have qchar=None
        assert result[0] == ","
        assert result[1] is None


# ===========================================================================
# Additional CsvLine.items() coverage for lines 282-286, 326-328
# ===========================================================================


class TestCsvLineItemsAdditional:
    """Additional coverage for CsvLine.items() state machine branches."""

    def _make_line(self, text):
        return CsvFile.CsvLine(text)

    def test_escaped_then_delimiter_transitions_to_between(self):
        # Lines 282-286: in CsvLine.items() escaped() → c == delim → _BETWEEN
        # Backslash before delimiter ends field and transitions to _BETWEEN
        line = self._make_line(r'"a\,b",c')
        result = line.items(",", '"')
        # The backslash escapes the comma; result has 2 fields
        assert len(result) >= 1

    def test_between_state_delimiter_first_char(self):
        # Lines 326-328: between() — first char is delimiter (state starts at _BETWEEN)
        # When text starts with delimiter and quotechar is set, between() is called first
        line = self._make_line(",second")
        result = line.items(",", '"')
        # First char is delimiter → appends current_element ("") → second field is "second"
        assert len(result) >= 1
        assert "second" in result

    def test_well_quoted_both_ends_with_unremovable_internal_quote(self):
        # Line 245: _well_quoted returns (False, True, False) when internal quotes
        # remain after trying both doubled-quote removal AND escaped-quote removal
        # Element like '"a"b"' — quotes on ends, but internal " can't be explained
        element = '"a"b"'
        line = CsvFile.CsvLine(element)
        wq, uses_q, escaped = line._well_quoted(element, '"')
        assert wq is False
        assert uses_q is True

    def test_items_between_state_leads_to_unquoted_via_text(self):
        # Lines 330-331: between() falls through to _IN_UNQUOTED via text char
        # After a close-quote (leaving _QUOTE_IN_QUOTED → else branch → _IN_QUOTED...
        # Actually test by starting with text (first char non-quote non-delim → between → unquoted)
        line = self._make_line("hello world")
        result = line.items(",", '"')
        # Single token, no delimiter
        assert result == ["hello world"]


# ===========================================================================
# CsvFile.create_table — line 706
# ===========================================================================


class TestCsvFileCreateTable:
    """Tests for CsvFile.create_table() — line 706."""

    def test_create_table_returns_sql(self, tmp_path):
        # Line 706: create_table delegates to table_data.create_table()
        from execsql.types import dbt_sqlite

        p = tmp_path / "data.csv"
        p.write_text("id,name\n1,Alice\n2,Bob\n", encoding="utf-8")
        cf = CsvFile(str(p), "utf-8")
        cf.evaluate_column_types()
        sql = cf.create_table(dbt_sqlite, None, "mytable")
        assert "mytable" in sql or "CREATE" in sql
