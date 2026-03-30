from __future__ import annotations

"""
CSV and delimited-text export for execsql.

Provides:

- :class:`LineDelimiter` — configurable line-ending constant.
- :class:`DelimitedWriter` / :class:`CsvWriter` — low-level writers used
  by the export logic.
- :class:`CsvFile` — full delimited-file reader/writer (≈622 lines in the
  original monolith) supporting custom delimiters, quoting, encoding, and
  ZIP output.
- :func:`write_delimited_file` — writes a query result set to a
  CSV/TSV/delimited text file.
"""

import copy
import re
import sys
from typing import Any

from execsql.utils.fileio import EncodedFile
from execsql.exporters.zip import ZipWriter
import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.models import DataTable
from execsql.utils.errors import exception_desc
from execsql.utils.fileio import filewriter_close
from execsql.utils.strings import clean_words, fold_words

__all__ = ["LineDelimiter", "CsvFile", "CsvWriter", "DelimitedWriter", "write_delimited_file"]


class LineDelimiter:
    def __init__(self, delim: str | None, quote: str | None, escchar: str | None) -> None:
        self.delimiter = delim
        self.joinchar = delim if delim else ""
        self.quotechar = quote
        if quote:
            if escchar:
                self.quotedquote = escchar + quote
            else:
                self.quotedquote = quote + quote
        else:
            self.quotedquote = None

    def delimited(self, datarow: Any, add_newline: bool = True) -> str:
        conf = _state.conf
        if self.quotechar:
            d_row = []
            for e in datarow:
                if isinstance(e, str):
                    if (
                        conf.quote_all_text
                        or (self.quotechar in e)
                        or (self.delimiter is not None and self.delimiter in e)
                        or ("\n" in e)
                        or ("\r" in e)
                    ):
                        d_row.append(f"{self.quotechar}{e.replace(self.quotechar, self.quotedquote)}{self.quotechar}")
                    else:
                        d_row.append(e)
                else:
                    if e is None:
                        d_row.append("")
                    else:
                        d_row.append(e)
            text = self.joinchar.join([str(d) for d in d_row])
        else:
            d_row = []
            for e in datarow:
                if e is None:
                    d_row.append("")
                else:
                    d_row.append(e)
            text = self.joinchar.join([str(d) for d in d_row])
        if add_newline:
            text = text + "\n"
        return text


class DelimitedWriter:
    def __init__(self, outfile: Any, delim: str | None, quote: str | None, escchar: str | None) -> None:
        self.outfile = outfile
        self.line_delimiter = LineDelimiter(delim, quote, escchar)

    def write(self, text_str: str) -> None:
        self.outfile.write(text_str)

    def writerow(self, datarow: Any) -> None:
        self.outfile.write(self.line_delimiter.delimited(datarow))

    def writerows(self, datarows: Any) -> None:
        for row in datarows:
            self.writerow(row)


class CsvWriter:
    def __init__(
        self,
        filename: str,
        file_encoding: str,
        delim: str | None,
        quote: str | None,
        escchar: str | None,
        append: bool = False,
    ) -> None:
        mode = "wt" if not append else "at"
        if filename.lower() == "stdout":
            self.output = sys.stdout
        else:
            filewriter_close(filename)
            self.output = EncodedFile(filename, file_encoding).open(mode)
        self.dwriter = DelimitedWriter(self.output, delim, quote, escchar)

    def write(self, text_str: str) -> None:
        self.dwriter.write(text_str)

    def writerow(self, datarow: Any) -> None:
        self.dwriter.writerow(datarow)

    def writerows(self, datarows: Any) -> None:
        self.dwriter.writerows(datarows)

    def close(self) -> None:
        self.output.close()
        self.output = None


class CsvFile(EncodedFile):
    def __init__(self, csvfname: str, file_encoding: str, junk_header_lines: int = 0) -> None:
        super().__init__(csvfname, file_encoding)
        self.csvfname = csvfname
        self.junk_header_lines = junk_header_lines
        self.lineformat_set = False  # Indicates whether delimiter, quotechar, and escapechar have been set
        self.delimiter = None
        self.quotechar = None
        self.escapechar = None
        self.parse_errors = []
        self.table_data = None  # Set to a DataTable object by 'evaluate_column_types()'
        self.blank_cols = []  # Indexes of blank column headers--columns may be deleted

    def __repr__(self) -> str:
        return f"CsvFile({self.csvfname!r}, {self.encoding!r})"

    def openclean(self, mode: str) -> Any:
        # Returns an opened file object with junk headers stripped.
        f = self.open(mode)
        for _ in range(self.junk_header_lines):
            f.readline()
        return f

    def lineformat(self, delimiter: str | None, quotechar: str | None, escapechar: str | None) -> None:
        # Specifies the format of a line.
        self.delimiter = delimiter
        self.quotechar = quotechar
        self.escapechar = escapechar
        self.lineformat_set = True

    class CsvLine:
        escchar = "\\"

        def __init__(self, line_text: str) -> None:
            self.text = line_text
            self.delim_counts = {}
            self.item_errors = []  # A list of error messages.

        def __str__(self) -> str:
            return "; ".join(
                [
                    f"Text: <<{self.text}>>",
                    "Delimiter counts: <<{}>>".format(
                        ", ".join([f"{k}: {self.delim_counts[k]}" for k in self.delim_counts]),
                    ),
                ],
            )

        def count_delim(self, delim: str) -> None:
            # If the delimiter is a space, consider multiple spaces to be equivalent
            # to a single delimiter, split on the space(s), and consider the delimiter
            # count to be one fewer than the items returned.
            if delim == " ":
                self.delim_counts[delim] = max(0, len(re.split(r" +", self.text)) - 1)
            else:
                self.delim_counts[delim] = self.text.count(delim)

        def delim_count(self, delim: str) -> int:
            return self.delim_counts[delim]

        def _well_quoted(self, element: str, qchar: str):
            # A well-quoted element has either no quotes, a quote on each end and none
            # in the middle, or quotes on both ends and every internal quote is either
            # doubled or escaped.
            # Returns a tuple of three booleans; the first indicates whether the element is
            # well-quoted, the second indicates whether the quote character is used
            # at all, and the third indicates whether the escape character is used.
            if qchar not in element:
                return (True, False, False)
            if len(element) == 0:
                return (True, False, False)
            if element[0] == qchar and element[-1] == qchar and qchar not in element[1:-1]:
                return (True, True, False)
            # The element has quotes; if it doesn't have one on each end, it is not well-quoted.
            if not (element[0] == qchar and element[-1] == qchar):
                return (False, True, False)
            e = element[1:-1]
            # If there are no quotes left after removing doubled quotes, this is well-quoted.
            if qchar not in e.replace(qchar + qchar, ""):
                return (True, True, False)
            # if there are no quotes left after removing escaped quotes, this is well-quoted.
            if qchar not in e.replace(self.escchar + qchar, ""):
                return (True, True, True)
            return (False, True, False)

        def record_format_error(self, pos_no: int, errmsg: str) -> None:
            self.item_errors.append(f"{errmsg} in position {pos_no}.")

        def items(self, delim: str | None, qchar: str | None) -> Any:
            # Parses the line into a list of items, breaking it at delimiters that are not
            # within quoted stretches.
            self.item_errors = []
            if qchar is None:
                if delim is None:
                    return self.text
                if delim == " ":
                    return re.split(r" +", self.text)
                else:
                    return self.text.split(delim)
            elements = []  # The list of items on the line that will be returned.
            eat_multiple_delims = delim == " "
            _IN_QUOTED, _ESCAPED, _QUOTE_IN_QUOTED, _IN_UNQUOTED, _BETWEEN, _DELIMITED = range(6)
            esc_buf = [""]
            current_element = [""]

            def in_quoted():
                if c == self.escchar:
                    esc_buf[0] = c
                    return _ESCAPED
                elif c == qchar:
                    esc_buf[0] = c
                    return _QUOTE_IN_QUOTED
                else:
                    current_element[0] += c
                    return _IN_QUOTED

            def escaped():
                if c == delim:
                    current_element[0] += esc_buf[0]
                    esc_buf[0] = ""
                    elements.append(current_element[0])
                    current_element[0] = ""
                    return _BETWEEN
                else:
                    current_element[0] += esc_buf[0]
                    esc_buf[0] = ""
                    current_element[0] += c
                    return _IN_QUOTED

            def quote_in_quoted():
                if c == qchar:
                    current_element[0] += esc_buf[0]
                    esc_buf[0] = ""
                    current_element[0] += c
                    return _IN_QUOTED
                elif c == delim:
                    current_element[0] += esc_buf[0]
                    esc_buf[0] = ""
                    elements.append(current_element[0])
                    current_element[0] = ""
                    return _DELIMITED
                else:
                    current_element[0] += esc_buf[0]
                    esc_buf[0] = ""
                    current_element[0] += c
                    self.record_format_error(i + 1, "Unexpected character following a closing quote")
                    return _IN_QUOTED

            def in_unquoted():
                if c == delim:
                    elements.append(current_element[0])
                    current_element[0] = ""
                    return _DELIMITED
                else:
                    current_element[0] += c
                    return _IN_UNQUOTED

            def between():
                if c == qchar:
                    current_element[0] += c
                    return _IN_QUOTED
                elif c == delim:
                    elements.append(current_element[0])
                    current_element[0] = ""
                    return _DELIMITED
                else:
                    current_element[0] += c
                    return _IN_UNQUOTED

            def delimited():
                if c == qchar:
                    current_element[0] += c
                    return _IN_QUOTED
                elif c == delim:
                    if not eat_multiple_delims:
                        elements.append(current_element[0])
                        current_element[0] = ""
                    return _DELIMITED
                else:
                    current_element[0] += c
                    return _IN_UNQUOTED

            exec_vector = [in_quoted, escaped, quote_in_quoted, in_unquoted, between, delimited]
            state = _BETWEEN
            for i, c in enumerate(self.text):  # noqa: B007
                state = exec_vector[state]()
            if len(esc_buf[0]) > 0:
                current_element[0] += esc_buf[0]
            if len(current_element[0]) > 0:
                elements.append(current_element[0])
            if len(self.item_errors) > 0:
                raise ErrInfo("error", other_msg=", ".join(self.item_errors))
            return elements

        def well_quoted_line(self, delim: str | None, qchar: str | None):
            # Returns a tuple of boolean, int, and boolean
            wq = [self._well_quoted(el, qchar) for el in self.items(delim, qchar)]
            return (all(b[0] for b in wq), sum([b[1] for b in wq]), any(b[2] for b in wq))

    def diagnose_delim(
        self,
        linestream: Any,
        possible_delimiters: list[str] | None = None,
        possible_quotechars: list[str] | None = None,
    ):
        # Returns a tuple consisting of the delimiter, quote character, and escape
        # character for quote characters within elements of a line.  All may be None.
        conf = _state.conf
        if not possible_delimiters:
            possible_delimiters = ["\t", ",", ";", "|", chr(31)]
        if not possible_quotechars:
            possible_quotechars = ['"', "'"]
        lines = []
        for _i in range(conf.scan_lines if conf.scan_lines and conf.scan_lines > 0 else 1000000):
            try:
                ln = next(linestream)
            except StopIteration:
                break
            except:
                raise
            while len(ln) > 0 and ln[-1] in ("\n", "\r"):
                ln = ln[:-1]
            if len(ln) > 0:
                lines.append(self.CsvLine(ln))
        if len(lines) == 0:
            raise ErrInfo(type="error", other_msg="CSV diagnosis error: no lines read")
        for ln in lines:
            for d in possible_delimiters:
                ln.count_delim(d)
        delim_stats = {}
        for d in possible_delimiters:
            dcounts = [ln.delim_count(d) for ln in lines]
            min_count = min(dcounts)
            delim_stats[d] = (min_count, dcounts.count(min_count))
        no_delim = []
        for k in delim_stats:
            if delim_stats[k][0] == 0:
                no_delim.append(k)
        for k in no_delim:
            del delim_stats[k]

        def all_well_quoted(delim, qchar):
            wq = [ln.well_quoted_line(delim, qchar) for ln in lines]
            return (
                all(b[0] for b in wq),
                sum([b[1] for b in wq]),
                self.CsvLine.escchar if any(b[2] for b in wq) else None,
            )

        def eval_quotes(delim):
            ok_quotes = {}
            for q in possible_quotechars:
                allwq = all_well_quoted(delim, q)
                if allwq[0]:
                    ok_quotes[q] = (allwq[1], allwq[2])
            if len(ok_quotes) == 0:
                return (delim, None, None)
            else:
                max_use = max([v[0] for v in ok_quotes.values()])
                if max_use == 0:
                    return (delim, None, None)
                for q in ok_quotes:
                    if ok_quotes[q][0] == max_use:
                        return (delim, q, ok_quotes[q][1])

        if len(delim_stats) == 0:
            return eval_quotes(None)
        else:
            if len(delim_stats) > 1 and " " in delim_stats:
                del delim_stats[" "]
            if len(delim_stats) == 1:
                return eval_quotes(list(delim_stats)[0])
            delim_wts = {}
            for d in delim_stats:
                delim_wts[d] = delim_stats[d][0] ** 2 * delim_stats[d][1]
            delim_order = sorted(delim_wts, key=delim_wts.get, reverse=True)
            for d in delim_order:
                quote_check = eval_quotes(d)
                if quote_check[0] and quote_check[1]:
                    return quote_check
            return (delim_order[0], None, None)
        raise ErrInfo(
            type="error",
            other_msg="CSV diagnosis coding error: an untested set of conditions are present",
        )

    def evaluate_line_format(self) -> None:
        # Scans the file to determine the delimiter, quote character, and escapechar.
        if not self.lineformat_set:
            f = self.openclean("rt")
            try:
                self.delimiter, self.quotechar, self.escapechar = self.diagnose_delim(f)
            finally:
                f.close()
            self.lineformat_set = True

    def _record_format_error(self, pos_no: int, errmsg: str) -> None:
        self.parse_errors.append(f"{errmsg} in position {pos_no}")

    def read_and_parse_line(self, f: Any) -> list:
        # Returns a list of line elements, parsed according to the established delimiter and quotechar.
        elements = []
        eat_multiple_delims = self.delimiter == " "
        _START, _IN_QUOTED, _ESCAPED, _QUOTE_IN_QUOTED, _IN_UNQUOTED, _BETWEEN, _DELIMITED, _END = range(8)
        esc_buf = [""]
        current_element = [""]

        def start():
            if c == self.quotechar:
                return _IN_QUOTED
            elif c == self.delimiter:
                elements.append(None)
                return _DELIMITED
            elif c == "\n":
                return _END
            else:
                current_element[0] += c
                return _IN_UNQUOTED

        def in_quoted():
            if c == self.escapechar:
                esc_buf[0] = c
                return _ESCAPED
            elif c == self.quotechar:
                esc_buf[0] = c
                return _QUOTE_IN_QUOTED
            else:
                current_element[0] += c
                return _IN_QUOTED

        def escaped():
            if c == self.quotechar:
                esc_buf[0] = ""
                current_element[0] += c
                return _IN_QUOTED
            elif c == self.delimiter:
                current_element[0] += esc_buf[0]
                esc_buf[0] = ""
                current_element[0] += c
                return _IN_QUOTED
            else:
                current_element[0] += esc_buf[0]
                esc_buf[0] = ""
                current_element[0] += c
                return _IN_QUOTED

        def quote_in_quoted():
            if c == self.quotechar:
                esc_buf[0] = ""
                current_element[0] += c
                return _IN_QUOTED
            elif c == self.delimiter:
                esc_buf[0] = ""
                elements.append(current_element[0])
                current_element[0] = ""
                return _DELIMITED
            elif c == "\n":
                esc_buf[0] = ""
                elements.append(current_element[0])
                current_element[0] = ""
                return _END
            else:
                esc_buf[0] = ""
                elements.append(current_element[0] if len(current_element[0]) > 0 else None)
                current_element[0] += c
                self._record_format_error(i, "Unexpected character following a closing quote")
                return _IN_UNQUOTED

        def in_unquoted():
            if c == self.delimiter:
                elements.append(current_element[0] if len(current_element[0]) > 0 else None)
                current_element[0] = ""
                return _DELIMITED
            elif c == "\n":
                elements.append(current_element[0] if len(current_element[0]) > 0 else None)
                current_element[0] = ""
                return _END
            elif c == self.quotechar:
                elements.append(current_element[0] if len(current_element[0]) > 0 else None)
                current_element[0] = ""
                return _IN_QUOTED
            else:
                current_element[0] += c
                return _IN_UNQUOTED

        def between():
            if c == self.quotechar:
                return _IN_QUOTED
            elif c == self.delimiter:
                current_element[0] = ""
                return _DELIMITED
            elif c == "\n":
                return _END
            else:
                current_element[0] += c
                self._record_format_error(i, "Unexpected character following a closing quote")
                return _IN_UNQUOTED

        def delimited():
            if c == self.quotechar:
                return _IN_QUOTED
            elif c == self.delimiter:
                if not eat_multiple_delims:
                    elements.append(current_element[0] if len(current_element[0]) > 0 else None)
                    current_element[0] = ""
                return _DELIMITED
            elif c == "\n":
                return _END
            else:
                current_element[0] += c
                return _IN_UNQUOTED

        def end():
            if len(esc_buf[0]) > 0 and prev_state == _ESCAPED:
                current_element[0] += esc_buf[0]
            if len(current_element[0]) > 0:
                if prev_state == _QUOTE_IN_QUOTED:
                    elements.append(current_element[0][:-1])
                else:
                    elements.append(current_element[0])
            if prev_state == _DELIMITED:
                elements.append(None)
            return None

        exec_vector = [start, in_quoted, escaped, quote_in_quoted, in_unquoted, between, delimited, end]
        state = _START
        prev_state = None
        i = 0
        self.parse_errors = []
        while state != _END:
            c = f.read(1)
            if c == "\n":
                i = 0
            if c == "":
                state = _END
            else:
                i += 1
                prev_state = state
                state = exec_vector[state]()
        end()
        if len(self.parse_errors) > 0:
            raise ErrInfo("error", other_msg=", ".join(self.parse_errors))
        return elements

    def reader(self) -> Any:
        conf = _state.conf
        self.evaluate_line_format()
        f = self.openclean("rt")
        line_no = 0
        try:
            while True:
                line_no += 1
                try:
                    elements = self.read_and_parse_line(f)
                except ErrInfo as e:
                    raise ErrInfo("error", other_msg=f"{e.other} on line {line_no}.") from e
                except:
                    raise
                if len(elements) > 0:
                    if conf.del_empty_cols and len(self.blank_cols) > 0:
                        blanks = copy.copy(self.blank_cols)
                        while len(blanks) > 0:
                            b = blanks.pop()
                            del elements[b]
                    yield elements
                else:
                    break
        finally:
            f.close()

    def writer(self, append: bool = False) -> CsvWriter:
        return CsvWriter(self.filename, self.encoding, self.delimiter, self.quotechar, self.escapechar, append)

    def _colhdrs(self, inf: Any) -> list[str]:
        conf = _state.conf
        try:
            colnames = next(inf)
        except ErrInfo as e:
            e.other = f"Can't read column header line from {self.filename}.  {e.other or ''}"
            raise
        except Exception as e:
            raise ErrInfo(
                type="exception",
                exception_msg=exception_desc(),
                other_msg=f"Can't read column header line from {self.filename}",
            ) from e
        if any(x is None or len(x) == 0 for x in colnames):
            if conf.del_empty_cols:
                self.blank_cols = [
                    i for i in range(len(colnames)) if colnames[i] is None or len(colnames[i].strip()) == 0
                ]
                blanks = copy.copy(self.blank_cols)
                while len(blanks) > 0:
                    b = blanks.pop()
                    del colnames[b]
            else:
                if conf.create_col_hdrs:
                    for i in range(len(colnames)):
                        if colnames[i] is None or len(colnames[i]) == 0:
                            colnames[i] = f"Col{i + 1}"
                else:
                    raise ErrInfo(
                        type="error",
                        other_msg=f"The input file {self.csvfname} has missing column headers.",
                    )
        if conf.clean_col_hdrs:
            colnames = clean_words(colnames)
        if conf.fold_col_hdrs != "no":
            colnames = fold_words(colnames, conf.fold_col_hdrs)
        if conf.dedup_col_hdrs:
            colnames = _state.dedup_words(colnames)
        return colnames

    def column_headers(self) -> list[str]:
        if not self.lineformat_set:
            self.evaluate_line_format()
        inf = self.reader()
        return self._colhdrs(inf)

    def data_table_def(self) -> Any:
        if self.table_data is None:
            self.evaluate_column_types()
        return self.table_data

    def evaluate_column_types(self) -> None:
        if not self.lineformat_set:
            self.evaluate_line_format()
        inf = self.reader()
        colnames = self._colhdrs(inf)
        self.table_data = DataTable(colnames, inf)

    def create_table(self, database_type: Any, schemaname: str | None, tablename: str, pretty: bool = False) -> str:
        return self.table_data.create_table(database_type, schemaname, tablename, pretty)


def write_delimited_file(
    outfile: str,
    filefmt: str,
    column_headers: list[str],
    rowsource: Any,
    file_encoding: str = "utf8",
    append: bool = False,
    zipfile: str | None = None,
) -> None:
    delim = None
    quote = None
    escchar = None
    if filefmt.lower() == "csv":
        delim = ","
        quote = '"'
        escchar = None
    elif filefmt.lower() in ("tab", "tsv"):
        delim = "\t"
        quote = None
        escchar = None
    elif filefmt.lower() in ("tabq", "tsvq"):
        delim = "\t"
        quote = '"'
        escchar = None
    elif filefmt.lower() in ("unitsep", "us"):
        delim = chr(31)
        quote = None
        escchar = None
    elif filefmt.lower() == "plain":
        delim = " "
        quote = ""
        escchar = None
    elif filefmt.lower() == "latex":
        delim = "&"
        quote = ""
        escchar = None
    line_delimiter = LineDelimiter(delim, quote, escchar)
    if zipfile is not None:
        ofile = ZipWriter(zipfile, outfile, append)
        fdesc = f"{outfile} in {zipfile}"
    else:
        fmode = "w" if not append else "a"
        filewriter_close(outfile)
        ofile = EncodedFile(outfile, file_encoding).open(mode=fmode)
        fdesc = outfile
    try:
        if not (filefmt.lower() == "plain" or (append and zipfile is None)):
            datarow = line_delimiter.delimited(column_headers)
            ofile.write(datarow)
        for rec in rowsource:
            try:
                datarow = line_delimiter.delimited(rec)
                ofile.write(datarow)
            except ErrInfo:
                raise
            except Exception as e:
                raise ErrInfo(
                    "exception",
                    exception_msg=exception_desc(),
                    other_msg=f"Can't write output to file {fdesc}.",
                ) from e
    finally:
        ofile.close()
