from __future__ import annotations

"""
Template-based report generation for execsql.

Provides :class:`StrTemplateReport` (Python :class:`string.Template`
substitution) and :func:`report_query`, which drives the
``EXPORT … FORMAT str-template``, ``FORMAT jinja``, and
``FORMAT airspeed`` metacommand variants.  Jinja2 and Airspeed template
processors are loaded lazily when selected.
"""

from typing import Any, Optional

import execsql.state as _state


class StrTemplateReport:
    # Exporting/reporting using Python's default string.Template, iterated over all
    # rows of a data table.
    def __init__(self, template_file: str) -> None:
        global string
        import string

        conf = _state.conf
        self.infname = template_file
        from execsql.utils.fileio import EncodedFile

        inf = EncodedFile(self.infname, conf.script_encoding)
        self.template = string.Template(inf.open("r").read())
        inf.close()

    def __repr__(self) -> str:
        return f"StrTemplateReport({self.infname})"

    def write_report(
        self,
        headers: Any,
        data_dict_rows: Any,
        output_dest: str,
        append: bool = False,
        zipfile: Optional[str] = None,
    ) -> None:
        conf = _state.conf
        from execsql.utils.fileio import EncodedFile
        from execsql.exporters.zip import ZipWriter

        if output_dest == "stdout":
            ofile = _state.output
        else:
            if zipfile is None:
                _state.filewriter_close(output_dest)
                if append:
                    ofile = EncodedFile(output_dest, conf.output_encoding).open("a")
                else:
                    ofile = EncodedFile(output_dest, conf.output_encoding).open("w")
            else:
                ofile = ZipWriter(zipfile, output_dest, append)
        for dd in data_dict_rows:
            ofile.write(self.template.safe_substitute(dd))
        if output_dest != "stdout":
            ofile.close()


class JinjaTemplateReport:
    # Exporting/reporting using the Jinja2 templating library.
    def __init__(self, template_file: str) -> None:
        global jinja2
        try:
            import jinja2
        except:
            _state.fatal_error(
                "The jinja2 library is required to produce reports with the Jinja2 templating system.   See http://jinja.pocoo.org/",
            )
        conf = _state.conf
        self.infname = template_file
        from execsql.utils.fileio import EncodedFile

        inf = EncodedFile(template_file, conf.script_encoding)
        self.template = jinja2.Template(inf.open("r").read())
        inf.close()

    def __repr__(self) -> str:
        return f"StrTemplateReport({self.infname})"

    def write_report(
        self,
        headers: Any,
        data_dict_rows: Any,
        output_dest: str,
        append: bool = False,
        zipfile: Optional[str] = None,
    ) -> None:
        conf = _state.conf
        from execsql.utils.fileio import EncodedFile
        from execsql.exporters.zip import ZipWriter

        if output_dest == "stdout":
            ofile = _state.output
        else:
            if zipfile is None:
                _state.filewriter_close(output_dest)
                if append:
                    ofile = EncodedFile(output_dest, conf.output_encoding).open("a")
                else:
                    ofile = EncodedFile(output_dest, conf.output_encoding).open("w")
            else:
                ofile = ZipWriter(zipfile, output_dest, append)
        try:
            ofile.write(self.template.render(headers=headers, datatable=data_dict_rows))
        except jinja2.TemplateSyntaxError as e:
            raise _state.ErrInfo("error", other_msg=e.message + f" on template line {e.lineno}")
        except jinja2.TemplateError as e:
            raise _state.ErrInfo("error", other_msg=f"Jinja2 template error ({e.message})")
        except:
            raise
        if output_dest != "stdout":
            ofile.close()


class AirspeedTemplateReport:
    # Exporting/reporting using the Airspeed templating library.
    def __init__(self, template_file: str) -> None:
        global airspeed
        try:
            import airspeed
        except:
            _state.fatal_error(
                "The airspeed library is required to produce reports with the Airspeed templating system.   See https://github.com/purcell/airspeed",
            )
        conf = _state.conf
        self.infname = template_file
        from execsql.utils.fileio import EncodedFile

        inf = EncodedFile(template_file, conf.script_encoding)
        self.template = airspeed.Template(inf.open("r").read())

    def __repr__(self) -> str:
        return f"StrTemplateReport({self.infname})"

    def write_report(
        self,
        headers: Any,
        data_dict_rows: Any,
        output_dest: str,
        append: bool = False,
        zipfile: Optional[str] = None,
    ) -> None:
        # airspeed requires an entire list to be passed, not just an iterable,
        # so produce a list of dictionaries.  This may be too big for memory if
        # the data set is very large.
        conf = _state.conf
        from execsql.utils.fileio import EncodedFile
        from execsql.exporters.zip import ZipWriter

        data = [d for d in data_dict_rows]
        if output_dest == "stdout":
            ofile = _state.output
        else:
            if zipfile is None:
                _state.filewriter_close(output_dest)
                if append:
                    ofile = EncodedFile(output_dest, conf.output_encoding).open("a")
                else:
                    ofile = EncodedFile(output_dest, conf.output_encoding).open("w")
            else:
                ofile = ZipWriter(zipfile, output_dest, append)
        try:
            ofile.write(self.template.merge({"headers": headers, "datatable": data}))
        except airspeed.TemplateExecutionError as e:
            raise _state.ErrInfo("error", other_msg=e.msg)
        except:
            raise
        if output_dest != "stdout":
            ofile.close()


def report_query(
    select_stmt: str,
    db: Any,
    outfile: str,
    template_file: str,
    append: bool = False,
    zipfile: Optional[str] = None,
) -> None:
    # Write (export) a template-based report.
    conf = _state.conf
    _state.status.sql_error = False
    headers, ddict = db.select_rowdict(select_stmt)
    if conf.template_processor == "jinja":
        t = JinjaTemplateReport(template_file)
    elif conf.template_processor == "airspeed":
        t = AirspeedTemplateReport(template_file)
    else:
        t = StrTemplateReport(template_file)
    t.write_report(headers, ddict, outfile, append, zipfile=zipfile)
