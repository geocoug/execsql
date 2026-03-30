from __future__ import annotations

"""
Template-based report generation for execsql.

Provides :class:`StrTemplateReport` (Python :class:`string.Template`
substitution) and :func:`report_query`, which drives the
``EXPORT … FORMAT str-template`` and ``FORMAT jinja`` metacommand
variants.  The Jinja2 template processor is loaded lazily when selected.
"""

import string
from typing import Any

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.utils.errors import fatal_error
from execsql.utils.fileio import filewriter_close

__all__ = ["StrTemplateReport", "JinjaTemplateReport", "report_query"]


class StrTemplateReport:
    # Exporting/reporting using Python's default string.Template, iterated over all
    # rows of a data table.
    def __init__(self, template_file: str) -> None:
        conf = _state.conf
        self.infname = template_file
        from execsql.utils.fileio import EncodedFile

        inf = EncodedFile(self.infname, conf.script_encoding)
        fh = inf.open("r")
        try:
            self.template = string.Template(fh.read())
        finally:
            fh.close()

    def __repr__(self) -> str:
        return f"StrTemplateReport({self.infname})"

    def write_report(
        self,
        headers: Any,
        data_dict_rows: Any,
        output_dest: str,
        append: bool = False,
        zipfile: str | None = None,
    ) -> None:
        conf = _state.conf
        from execsql.utils.fileio import EncodedFile
        from execsql.exporters.zip import ZipWriter

        if output_dest == "stdout":
            ofile = _state.output
        else:
            if zipfile is None:
                filewriter_close(output_dest)
                if append:
                    ofile = EncodedFile(output_dest, conf.output_encoding).open("a")
                else:
                    ofile = EncodedFile(output_dest, conf.output_encoding).open("w")
            else:
                ofile = ZipWriter(zipfile, output_dest, append)
        try:
            for dd in data_dict_rows:
                ofile.write(self.template.safe_substitute(dd))
        finally:
            if output_dest != "stdout":
                ofile.close()


class JinjaTemplateReport:
    # Exporting/reporting using the Jinja2 templating library.
    def __init__(self, template_file: str) -> None:
        try:
            import jinja2
            from jinja2.sandbox import SandboxedEnvironment

            self._jinja2 = jinja2
        except ImportError:
            fatal_error(
                "The jinja2 library is required to produce reports with the Jinja2 templating system.   See http://jinja.pocoo.org/",
            )
        conf = _state.conf
        self.infname = template_file
        from execsql.utils.fileio import EncodedFile

        inf = EncodedFile(template_file, conf.script_encoding)
        fh = inf.open("r")
        try:
            self.template = SandboxedEnvironment().from_string(fh.read())
        finally:
            fh.close()

    def __repr__(self) -> str:
        return f"JinjaTemplateReport({self.infname})"

    def write_report(
        self,
        headers: Any,
        data_dict_rows: Any,
        output_dest: str,
        append: bool = False,
        zipfile: str | None = None,
    ) -> None:
        conf = _state.conf
        from execsql.utils.fileio import EncodedFile
        from execsql.exporters.zip import ZipWriter

        if output_dest == "stdout":
            ofile = _state.output
        else:
            if zipfile is None:
                filewriter_close(output_dest)
                if append:
                    ofile = EncodedFile(output_dest, conf.output_encoding).open("a")
                else:
                    ofile = EncodedFile(output_dest, conf.output_encoding).open("w")
            else:
                ofile = ZipWriter(zipfile, output_dest, append)
        try:
            ofile.write(self.template.render(headers=headers, datatable=data_dict_rows))
        except self._jinja2.TemplateSyntaxError as e:
            raise ErrInfo("error", other_msg=e.message + f" on template line {e.lineno}") from e
        except self._jinja2.TemplateError as e:
            raise ErrInfo("error", other_msg=f"Jinja2 template error ({e.message})") from e
        finally:
            if output_dest != "stdout":
                ofile.close()


def report_query(
    select_stmt: str,
    db: Any,
    outfile: str,
    template_file: str,
    append: bool = False,
    zipfile: str | None = None,
) -> None:
    # Write (export) a template-based report.
    conf = _state.conf
    _state.status.sql_error = False
    headers, ddict = db.select_rowdict(select_stmt)
    if conf.template_processor == "jinja":
        t = JinjaTemplateReport(template_file)
    else:
        t = StrTemplateReport(template_file)
    t.write_report(headers, ddict, outfile, append, zipfile=zipfile)
