from __future__ import annotations

"""
File I/O utilities for execsql.

Provides:

- :class:`EncodedFile` — opens files with a specific encoding and error
  handler; supports the script-, output-, and import-encoding settings.
- :class:`FileWriter` — asynchronous multiprocessing text-file writer
  used for export output to avoid blocking the main execution loop.
- :class:`Logger` — wraps a log file with timestamped write methods;
  mirrors output to stderr when ``tee_write_log`` is set.
- :class:`TempFileMgr` — registry of temporary files that are cleaned up
  on normal and abnormal exit.
- :func:`check_dir` — ensures an output directory exists (optionally
  creating it).
- :func:`file_size_date` — returns (size, mtime) for a file.
- Helper functions: ``filewriter_write``, ``filewriter_close``, etc.
"""

import atexit
import codecs
import collections
import errno
import io
import multiprocessing
import os
import queue
from pathlib import Path
import stat
import sys
import tempfile
import time
from encodings.aliases import aliases as codec_dict
from typing import Any

from execsql.exceptions import ErrInfo

__all__ = [
    "make_export_dirs",
    "check_dir",
    "FileWriter",
    "EncodedFile",
    "Logger",
    "TempFileMgr",
    "list_encodings",
    "filewriter_filestatus",
    "filewriter_write",
    "filewriter_open_as_new",
    "filewriter_close",
    "filewriter_close_all_after_write",
    "filewriter_closeall",
    "filewriter_shutdown",
    "filewriter_end",
]


def make_export_dirs(outfile: str) -> None:
    if outfile.lower() != "stdout":
        output_dir = str(Path(outfile).parent)
        if output_dir != "":
            output_dir = str(Path(output_dir))
            emsg = f"Can't create, or can't access, the directory {output_dir} to use for exported data."
            try:
                os.makedirs(output_dir)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise ErrInfo("exception", exception_msg=emsg) from e
            except Exception as e:
                raise ErrInfo("exception", exception_msg=emsg) from e


def check_dir(filename: str) -> None:
    if filename.lower() != "stdout":
        import execsql.state as _state

        conf = _state.conf
        if conf.make_export_dirs:
            make_export_dirs(filename)
        else:
            dn = str(Path(filename).parent)
            if dn != "" and not Path(dn).exists():
                raise ErrInfo(type="error", other_msg=f"The directory for file '{filename}' does not exist.")


class FileWriter(multiprocessing.Process):
    # An object of this class is intended to be used as a subprocess.
    # All files that are to be written to are kept open until explicitly closed or the object is destroyed.
    # When writing to a file is requested, the file will be opened if it is not already open.  If the
    # file cannot be opened for writing, the content to be written will be queued up and opening will
    # be re-tried until a specified interval has elapsed.  The purpose is to work around file-opening
    # conflicts that result from temporary locking of output files by backup or syncing processes.
    (
        CMD_WRITE,
        CMD_CLOSE_IF_OPEN,
        CMD_CLOSE_ALL,
        CMD_GET_STATUS,
        CMD_SHUTDOWN,
        CMD_OPEN_AS_NEW,
        CMD_CLOSE_ALL_AFTER_WRITE,
        CMD_CLOSED_STATUS,
        CMD_PING,
    ) = range(9)

    class FileControl:
        STATUS_OPEN, STATUS_WAITING, STATUS_UNOPENED, STATUS_CLOSED, STATUS_OPENFAILURE = range(5)

        def __init__(self, fn: str, open_timeout: int, encoding: str = "utf-8") -> None:
            self.filename = fn
            self.open_timeout = open_timeout
            self.encoding = encoding
            self.openmode = "a"
            self.handle = None
            self.status = self.STATUS_UNOPENED
            self.open_start_time = None
            self.fail_message_written = False
            self.output_queue: collections.deque = collections.deque()
            self.close_after_write = False

        def __del__(self) -> None:
            try:
                self.close()
            except Exception:
                pass  # Best-effort cleanup at interpreter shutdown.

        def write_queue(self) -> None:
            while len(self.output_queue) > 0:
                m = self.output_queue.pop()
                self.handle.write(m)
            if self.close_after_write:
                self.close_after_write = False
                self.close()

        def open_as_new(self) -> None:
            self.close()
            self.openmode = "w"

        def try_open(self) -> None:
            if self.status != self.STATUS_OPEN or self.handle is None:
                if self.open_start_time is None:
                    self.open_start_time = time.time()
                if time.time() - self.open_start_time < self.open_timeout:
                    try:
                        self.handle = open(  # noqa: SIM115
                            file=self.filename,
                            mode=self.openmode,
                            encoding=self.encoding,
                            errors="backslashreplace",
                        )
                    except Exception:
                        self.status = self.STATUS_WAITING
                    else:
                        self.status = self.STATUS_OPEN
                        self.openmode = "a"  # Return to default for next open command.
                        self.open_start_time = None
                        self.fail_message_written = False
                else:
                    self.status = self.STATUS_OPENFAILURE
                    if not self.fail_message_written:
                        sys.stderr.write(
                            f"Could not open {self.filename} for writing after retrying for {self.open_timeout} seconds",
                        )
                        self.fail_message_written = True

        def close(self) -> None:
            if self.status == self.STATUS_WAITING:
                qlen = len(self.output_queue)
                sys.stderr.write(
                    f"Closing {self.filename} while still trying to open it (locked by another process?) -- {qlen} item(s) in queue to be written",
                )
            if self.status == self.STATUS_OPEN and self.handle is not None:
                self.write_queue()
                self.handle.close()
                self.handle = None
            self.status = self.STATUS_CLOSED
            self.openmode = "a"  # Return this to the default in case it had been changed for the last open.

        def clean_close(self) -> None:
            if self.status == self.STATUS_WAITING:
                self.close_after_write = True
            else:
                self.close()

        def write(self, content: str) -> None:
            self.output_queue.appendleft(content)
            self.try_open()
            if self.status == self.STATUS_OPEN:
                self.write_queue()

    def __init__(
        self,
        input_queue: multiprocessing.Queue,
        return_msg_queue: multiprocessing.Queue,
        file_encoding: str = "utf-8",
        open_timeout: int = 600,
    ) -> None:
        # open_timeout is the maximum time, in seconds, that opening will be retried
        # if a file cannot be initially opened for writing.
        super().__init__()
        self.input_queue = input_queue
        self.return_msg_queue = return_msg_queue
        self.file_encoding = file_encoding
        self.open_timeout = open_timeout
        self.files: dict = {}
        self.active = True
        # Functions in execvec must be in the same order as the CMD enums.
        self.execvec = (
            self.write,
            self.close_if_open,
            self.close_all,
            self.status,
            self.shutdown,
            self.open_as_new,
            self.close_all_after_write,
            self.closed_status,
            self.ping,
        )

    def __del__(self) -> None:
        try:
            self.close_all()
        except Exception:
            pass  # Best-effort cleanup at interpreter shutdown.

    def close_all(self) -> None:
        for fc in getattr(self, "files", {}).values():
            fc.close()

    def close_if_open(self, fn: str) -> None:
        filename = str(Path(fn).resolve())
        if filename in self.files:
            fc = self.files[filename]
            fc.close()

    def closed_status(self) -> None:
        # Return CLOSED for anything other than OPEN or WAITING
        st = self.FileControl.STATUS_CLOSED
        for fc in self.files.values():
            if fc.status in (self.FileControl.STATUS_OPEN, self.FileControl.STATUS_WAITING):
                st = fc.status
                break
        self.return_msg_queue.put(st)

    def close_all_after_write(self) -> None:
        for fc in self.files.values():
            if fc.status != self.FileControl.STATUS_CLOSED:
                fc.clean_close()

    def ping(self, token: object) -> None:
        """Echo *token* back on the return queue — used to synchronize callers."""
        self.return_msg_queue.put(token)

    def open_as_new(self, fn: str) -> None:
        filename = str(Path(fn).resolve())
        if filename not in self.files:
            self.files[filename] = self.FileControl(
                filename,
                open_timeout=self.open_timeout,
                encoding=self.file_encoding,
            )
        fc = self.files[filename]
        fc.open_as_new()

    def status(self, fn: str) -> None:
        filename = str(Path(fn).resolve())
        if filename in self.files:
            self.return_msg_queue.put(self.files[filename].status)
        else:
            self.return_msg_queue.put(self.FileControl.STATUS_UNOPENED)

    def write(self, fn: str, content: str) -> None:
        filename = str(Path(fn).resolve())
        if filename not in self.files:
            self.files[filename] = self.FileControl(
                filename,
                open_timeout=self.open_timeout,
                encoding=self.file_encoding,
            )
        fc = self.files[filename]
        fc.write(content)

    def shutdown(self) -> None:
        self.active = False
        self.close_all()

    def run(self) -> None:
        # Messages in the input queue consist of a 2-tuple, of which the first element
        # is a command and the second is a tuple of arguments for the function indicated
        # by that command.
        while self.active:
            try:
                command, argtuple = self.input_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            self.execvec[command](*argtuple)


# Subprocess objects for asynchronous writing to text files.
# filewriter is initialized in main(), so it can take configurable arguments.
filewriter: FileWriter | None = None
fw_input: multiprocessing.Queue = multiprocessing.Queue()
fw_output: multiprocessing.Queue = multiprocessing.Queue()


def filewriter_filestatus(filename: str) -> int:
    fw_input.put((FileWriter.CMD_GET_STATUS, (filename,)))
    return fw_output.get()


def filewriter_write(filename: str, message: str) -> None:
    fw_input.put((FileWriter.CMD_WRITE, (filename, message)))


def filewriter_open_as_new(filename: str) -> None:
    # FileWriter opens files in append mode ("a") by default.  This ensures that it
    # will be opened in write mode ("w") instead.  If the file is open, it will be closed.
    fw_input.put((FileWriter.CMD_OPEN_AS_NEW, (filename,)))


def filewriter_close(filename: str) -> None:
    # This is intended to be used by the main process to ensure that a file
    # is closed before that process writes to it.
    fw_input.put((FileWriter.CMD_CLOSE_IF_OPEN, (filename,)))
    while filewriter_filestatus(filename) == FileWriter.FileControl.STATUS_OPEN:
        time.sleep(0.05)


def filewriter_close_all_after_write() -> None:
    fw_input.put((FileWriter.CMD_CLOSE_ALL_AFTER_WRITE, ()))
    all_closed = False
    while not all_closed:
        fw_input.put((FileWriter.CMD_CLOSED_STATUS, ()))
        close_status = fw_output.get()
        all_closed = close_status == FileWriter.FileControl.STATUS_CLOSED
        time.sleep(0.05)


def filewriter_closeall() -> None:
    fw_input.put((FileWriter.CMD_CLOSE_ALL, ()))


def filewriter_shutdown() -> None:
    fw_input.put((FileWriter.CMD_SHUTDOWN, ()))


def filewriter_end() -> None:
    try:
        filewriter_shutdown()
        filewriter.join()
    except Exception:
        pass  # Best-effort cleanup at interpreter shutdown.


class EncodedFile:
    # A class providing an open method for an encoded file, allowing reading
    # and writing using unicode, without explicit decoding or encoding.
    def __repr__(self) -> str:
        return f"EncodedFile({self.filename!r}, {self.encoding!r})"

    def __init__(self, filename: str, file_encoding: str) -> None:
        self.filename = filename
        self.encoding = file_encoding
        self.bom_length = 0

        def detect_by_bom(path: str, default_enc: str) -> tuple:
            # Detect whether a file starts with a BOM, and if it does, return the encoding.
            # Otherwise, return the default encoding specified.
            with open(path, "rb") as f:
                raw = f.read(4)
            for enc, boms, bom_len in (
                ("utf-8-sig", (codecs.BOM_UTF8,), 3),
                ("utf_16", (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE), 2),
                ("utf_32", (codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE), 4),
            ):
                if any(raw.startswith(bom) for bom in boms):
                    return enc, bom_len
            return default_enc, 0

        if Path(filename).exists():
            self.encoding, self.bom_length = detect_by_bom(filename, file_encoding)
        self.fo = None

    def open(self, mode: str = "r") -> io.TextIOWrapper:
        import execsql.state as _state

        conf = _state.conf
        self.fo = open(  # noqa: SIM115
            file=self.filename,
            mode=mode,
            encoding=self.encoding,
            errors=conf.enc_err_disposition,
            newline=None,
        )
        return self.fo

    def close(self) -> None:
        if self.fo is not None:
            self.fo.close()


class Logger:
    # A custom logger for execsql that writes several different types of messages to a log file.
    log_file = None

    def __repr__(self) -> str:
        return f"Logger({self.script_file_name!r}, {self.db_name!r}, {self.server_name!r}, {self.cmdline_options!r}, {self.log_file_name!r})"

    def __init__(
        self,
        script_file_name: str,
        db_name: str,
        server_name: str | None,
        cmdline_options: dict,
        user_logfile: bool = False,
        log_file_name: str | None = None,
    ) -> None:
        import getpass
        from execsql.utils.errors import exception_desc, exit_now, file_size_date

        # For Access and SQLite, 'db_name' should be the file name and 'server_name' should be null.
        self.script_file_name = script_file_name
        self.db_name = db_name
        self.server_name = server_name
        self.cmdline_options = cmdline_options
        if log_file_name:
            self.log_file_name = log_file_name
        else:
            if user_logfile:
                self.log_file_name = str(Path("~/execsql.log").expanduser())
            else:
                self.log_file_name = str(Path(os.getcwd()) / "execsql.log")
        self._rotate_if_needed()
        f_exists = Path(self.log_file_name).is_file()
        if f_exists:
            try:
                os.chmod(self.log_file_name, os.stat(self.log_file_name).st_mode | stat.S_IWRITE)
            except Exception:
                # Ignore exception; if the file is not set to writeable, opening it will raise an exception.
                pass
        try:
            import execsql.state as _state

            ef = EncodedFile(self.log_file_name, _state.logfile_encoding)
            self.log_file = ef.open("a")
        except Exception:
            errmsg = f"Can't open log file {self.log_file_name}"
            e = ErrInfo("exception", exception_msg=exception_desc(), other_msg=errmsg)
            exit_now(1, e, errmsg)
        if not f_exists:
            self.writelog(
                "# Execsql log.\n# The first value on each line is the record type.\n"
                "# The second value is the run identifier.\n# See the documentation for details.\n",
            )
        import datetime as _datetime

        _now = _datetime.datetime.now()
        self.run_start = _now
        self.run_id = _now.strftime("%Y%m%d_%H%M_%S_") + f"{_now.microsecond // 1000:03d}"
        self.user = getpass.getuser()
        if script_file_name and Path(script_file_name).is_file():
            sz, dt = file_size_date(script_file_name)
            abs_script = str(Path(script_file_name).resolve())
        else:
            sz, dt = 0, ""
            abs_script = script_file_name or "<inline>"
        msg = "run\t{}\t{}\t{}\t{}\t{}\t{}\n".format(
            self.run_id,
            abs_script,
            dt,
            sz,
            self.user,
            ", ".join([f"{k}: {cmdline_options[k]}" for k in cmdline_options]),
        )
        self.writelog(msg)
        if server_name:
            msg = f"run_db_server\t{self.run_id}\t{server_name}\t{db_name}\n"
        else:
            msg = f"run_db_file\t{self.run_id}\t{db_name}\n"
        self.writelog(msg)
        self.seq_no = 0
        atexit.register(self.close)
        self.exit_type = "unknown"
        self.exit_scriptfile = None
        self.exit_lno = None
        self.exit_description = None
        atexit.register(self.log_exit)

    def _ts(self) -> str:
        import datetime as _datetime

        return _datetime.datetime.now().isoformat(timespec="seconds")

    def _rotate_if_needed(self) -> None:
        try:
            import execsql.state as _state

            max_mb = getattr(_state.conf, "max_log_size_mb", 0) if _state.conf else 0
        except Exception:
            max_mb = 0
        if max_mb > 0 and Path(self.log_file_name).is_file():
            size_mb = Path(self.log_file_name).stat().st_size / (1024 * 1024)
            if size_mb >= max_mb:
                rotated = self.log_file_name + ".1"
                try:
                    if Path(rotated).exists():
                        os.remove(rotated)
                    os.rename(self.log_file_name, rotated)
                except Exception:
                    pass  # Log rotation is best-effort; file may be locked.

    def writelog(self, msg: str) -> None:
        if self.log_file is not None:
            self.log_file.write(msg)

    def close(self) -> None:
        if self.log_file:
            self.log_file.close()
            self.log_file = None

    def log_db_connect(self, db: Any) -> None:
        self.seq_no += 1
        msg = f"connect\t{self.run_id}\t{self.seq_no}\t{self._ts()}\t{db.name()}\n"
        self.writelog(msg)

    def log_action_export(self, line_no: int, query_name: str, export_file_name: str) -> None:
        self.seq_no += 1
        msg = f"action\t{self.run_id}\t{self.seq_no}\t{self._ts()}\texport\t{line_no}\tQuery {query_name} exported to {export_file_name}\n"
        self.writelog(msg)

    def log_status_exception(self, msg: str | None) -> None:
        msg = None if not msg else msg.replace("\n", "")
        self.seq_no += 1
        wmsg = f"status\t{self.run_id}\t{self.seq_no}\t{self._ts()}\texception\t{msg or ''}\n"
        self.writelog(wmsg)

    def log_status_error(self, msg: str | None) -> None:
        msg = None if not msg else msg.replace("\n", "")
        self.seq_no += 1
        wmsg = f"status\t{self.run_id}\t{self.seq_no}\t{self._ts()}\terror\t{msg or ''}\n"
        self.writelog(wmsg)

    def log_status_info(self, msg: str | None) -> None:
        msg = None if not msg else msg.replace("\n", "")
        self.seq_no += 1
        wmsg = f"status\t{self.run_id}\t{self.seq_no}\t{self._ts()}\tinfo\t{msg or ''}\n"
        self.writelog(wmsg)

    def log_status_warning(self, msg: str | None) -> None:
        msg = None if not msg else msg.replace("\n", "")
        self.seq_no += 1
        wmsg = f"status\t{self.run_id}\t{self.seq_no}\t{self._ts()}\twarning\t{msg or ''}\n"
        self.writelog(wmsg)

    def log_sql_query(self, sql: str, db_name: str, line_no: int | None = None) -> None:
        """Log an executed SQL statement for audit purposes."""
        cleaned = sql.replace("\n", " ").replace("\t", " ")
        if len(cleaned) > 2000:
            cleaned = cleaned[:2000] + "..."
        self.seq_no += 1
        lno = line_no if line_no is not None else 0
        wmsg = f"sql\t{self.run_id}\t{self.seq_no}\t{self._ts()}\t{db_name}\t{lno}\t{cleaned}\n"
        self.writelog(wmsg)

    def log_user_msg(self, msg: str | None) -> None:
        msg = None if not msg else msg.replace("\n", "")
        if msg != "":
            self.seq_no += 1
            wmsg = f"user_msg\t{self.run_id}\t{self.seq_no}\t{self._ts()}\tinfo\t{msg}\n"
            self.writelog(wmsg)

    def log_exit_end(self, script_file_name: str | None = None, line_no: int | None = None) -> None:
        # Save values to be used by exit() function triggered on program exit
        self.exit_type = "end_of_script"
        self.exit_scriptfile = script_file_name
        self.exit_lno = line_no
        self.exit_description = None

    def log_exit_halt(self, script_file_name: str, line_no: int, msg: str | None = None) -> None:
        # Save values to be used by exit() function triggered on program exit
        self.exit_type = "halt"
        self.exit_scriptfile = script_file_name
        self.exit_lno = line_no
        self.exit_description = msg

    def log_exit_exception(self, msg: str) -> None:
        # Save values to be used by exit() function triggered on program exit
        self.exit_type = "exception"
        self.exit_scriptfile = None
        self.exit_lno = None
        self.exit_description = msg.replace("\n", "")

    def log_exit_error(self, msg: str | None) -> None:
        # Save values to be used by exit() function triggered on program exit
        self.exit_type = "error"
        self.exit_scriptfile = None
        self.exit_lno = None
        self.exit_description = None if not msg else msg.replace("\n", "")

    def log_exit(self) -> None:
        import datetime as _datetime

        elapsed = (_datetime.datetime.now() - self.run_start).total_seconds()
        wmsg = "exit\t{}\t{}\t{}({})\t{}\t{:.1f}s\n".format(
            self.run_id,
            self.exit_type,
            self.exit_scriptfile or "",
            str(self.exit_lno or ""),
            self.exit_description or "",
            elapsed,
        )
        self.writelog(wmsg)


class TempFileMgr:
    def __repr__(self) -> str:
        return "TempFileMgr()"

    def __init__(self) -> None:
        # Initialize a list of temporary file names.
        self.temp_file_names: list = []
        atexit.register(self.remove_all)

    def new_temp_fn(self) -> str:
        # Create a temp file securely via mkstemp (avoids TOCTOU race).
        fd, fn = tempfile.mkstemp()
        os.close(fd)
        self.temp_file_names.append(fn)
        return fn

    def remove_all(self) -> None:
        for fn in self.temp_file_names:
            if Path(fn).exists():
                try:
                    # This may fail if the user has it open; let it go.
                    os.unlink(fn)
                except Exception:
                    pass


def list_encodings() -> None:
    enc = list(codec_dict.keys())
    enc.sort()
    msg = f"Encodings: {', '.join(enc)}\n"
    print(msg)
