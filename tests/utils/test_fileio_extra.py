"""Additional tests for execsql.utils.fileio — Logger methods, FileWriter.FileControl."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import execsql.state as _state
from execsql.utils.fileio import FileWriter, Logger


# ---------------------------------------------------------------------------
# Logger methods
# ---------------------------------------------------------------------------


class TestLoggerMethods:
    @pytest.fixture
    def logger(self, tmp_path, minimal_conf):
        _state.logfile_encoding = "utf-8"
        log_path = str(tmp_path / "test.log")
        lg = Logger(
            script_file_name="test.sql",
            db_name="testdb",
            server_name=None,
            cmdline_options={"verbose": True},
            log_file_name=log_path,
        )
        yield lg
        lg.close()

    def test_log_db_connect(self, logger):
        mock_db = MagicMock()
        mock_db.name.return_value = "testdb"
        logger.log_db_connect(mock_db)
        assert logger.seq_no == 1

    def test_log_action_export(self, logger):
        logger.log_action_export(42, "qry1", "output.csv")
        assert logger.seq_no == 1

    def test_log_status_exception(self, logger):
        logger.log_status_exception("something broke")
        assert logger.seq_no == 1

    def test_log_status_error(self, logger):
        logger.log_status_error("error msg")
        assert logger.seq_no == 1

    def test_log_status_info(self, logger):
        logger.log_status_info("info msg")
        assert logger.seq_no == 1

    def test_log_status_warning(self, logger):
        logger.log_status_warning("warning msg")
        assert logger.seq_no == 1

    def test_log_sql_query(self, logger):
        logger.log_sql_query("SELECT 1", "testdb", 5)
        assert logger.seq_no == 1

    def test_log_sql_query_long_truncated(self, logger):
        long_sql = "SELECT " + "x" * 3000
        logger.log_sql_query(long_sql, "testdb")
        assert logger.seq_no == 1

    def test_log_user_msg(self, logger):
        logger.log_user_msg("user message")
        assert logger.seq_no == 1

    def test_log_user_msg_empty_converts_to_none(self, logger):
        # "" is falsy so `not msg` is True → msg becomes None
        # None != "" is True → seq_no increments and logs "None"
        logger.log_user_msg("")
        assert logger.seq_no == 1

    def test_log_user_msg_none(self, logger):
        # None is falsy so `not msg` is True → msg stays None
        # None != "" is True → seq_no increments
        logger.log_user_msg(None)
        assert logger.seq_no == 1

    def test_log_exit_end(self, logger):
        logger.log_exit_end("test.sql", 100)
        assert logger.exit_type == "end_of_script"
        assert logger.exit_scriptfile == "test.sql"
        assert logger.exit_lno == 100

    def test_log_exit_halt(self, logger):
        logger.log_exit_halt("test.sql", 50, "User canceled")
        assert logger.exit_type == "halt"
        assert logger.exit_description == "User canceled"

    def test_log_exit_exception(self, logger):
        logger.log_exit_exception("traceback info")
        assert logger.exit_type == "exception"

    def test_log_exit_error(self, logger):
        logger.log_exit_error("fatal error")
        assert logger.exit_type == "error"
        assert logger.exit_description == "fatal error"

    def test_log_exit_writes_to_file(self, logger):
        logger.log_exit_end()
        logger.log_exit()
        logger.log_file.flush()
        with open(logger.log_file_name) as f:
            content = f.read()
        assert "exit" in content

    def test_writelog_none_file_is_noop(self, logger):
        logger.log_file = None
        logger.writelog("should not crash")  # must not raise


class TestLoggerWithServer:
    def test_server_name_in_log(self, tmp_path, minimal_conf):
        _state.logfile_encoding = "utf-8"
        log_path = str(tmp_path / "test.log")
        lg = Logger(
            script_file_name="test.sql",
            db_name="testdb",
            server_name="pghost.example.com",
            cmdline_options={},
            log_file_name=log_path,
        )
        lg.log_file.flush()
        with open(log_path) as f:
            content = f.read()
        assert "run_db_server" in content
        assert "pghost.example.com" in content
        lg.close()


class TestLoggerRotation:
    def test_rotation_when_size_exceeded(self, tmp_path, minimal_conf):
        _state.logfile_encoding = "utf-8"
        minimal_conf.max_log_size_mb = 0.0001  # Very small threshold

        log_path = tmp_path / "test.log"
        # Write enough data to exceed the threshold
        log_path.write_text("x" * 200)

        lg = Logger(
            script_file_name="test.sql",
            db_name="testdb",
            server_name=None,
            cmdline_options={},
            log_file_name=str(log_path),
        )
        # The rotated file should exist
        assert (tmp_path / "test.log.1").exists()
        lg.close()


class TestLoggerNoScriptFile:
    def test_logger_no_script_file(self, tmp_path, minimal_conf):
        _state.logfile_encoding = "utf-8"
        log_path = str(tmp_path / "test.log")
        lg = Logger(
            script_file_name=None,
            db_name="testdb",
            server_name=None,
            cmdline_options={},
            log_file_name=log_path,
        )
        lg.log_file.flush()
        with open(log_path) as f:
            content = f.read()
        assert "<inline>" in content
        lg.close()


# ---------------------------------------------------------------------------
# FileWriter.FileControl — additional coverage
# ---------------------------------------------------------------------------


class TestFileControlWrite:
    def test_write_queues_and_opens(self, tmp_path):
        fc = FileWriter.FileControl(str(tmp_path / "test.txt"), open_timeout=5)
        fc.write("hello\n")
        assert fc.status == fc.STATUS_OPEN
        fc.close()
        assert (tmp_path / "test.txt").read_text() == "hello\n"

    def test_write_appends_by_default(self, tmp_path):
        path = tmp_path / "test.txt"
        path.write_text("first\n")
        fc = FileWriter.FileControl(str(path), open_timeout=5)
        fc.write("second\n")
        fc.close()
        assert path.read_text() == "first\nsecond\n"

    def test_open_as_new_resets_to_write_mode(self, tmp_path):
        path = tmp_path / "test.txt"
        path.write_text("old content")
        fc = FileWriter.FileControl(str(path), open_timeout=5)
        fc.open_as_new()
        fc.write("new content\n")
        fc.close()
        assert path.read_text() == "new content\n"

    def test_close_when_already_closed_is_safe(self, tmp_path):
        fc = FileWriter.FileControl(str(tmp_path / "test.txt"), open_timeout=5)
        fc.close()
        fc.close()  # Should not raise

    def test_clean_close_when_not_waiting(self, tmp_path):
        fc = FileWriter.FileControl(str(tmp_path / "test.txt"), open_timeout=5)
        fc.write("data\n")
        fc.clean_close()
        assert fc.status == fc.STATUS_CLOSED

    def test_close_while_waiting_writes_stderr(self, tmp_path, capsys):
        fc = FileWriter.FileControl(str(tmp_path / "no_dir" / "test.txt"), open_timeout=5)
        fc.output_queue.appendleft("queued data")
        fc.status = fc.STATUS_WAITING
        fc.close()
        captured = capsys.readouterr()
        assert "Closing" in captured.err

    def test_open_failure_after_timeout(self, tmp_path, capsys):
        bad_path = str(tmp_path / "no_dir" / "test.txt")
        fc = FileWriter.FileControl(bad_path, open_timeout=0)
        fc.open_start_time = 0  # Force timeout
        fc.try_open()
        assert fc.status == fc.STATUS_OPENFAILURE
        captured = capsys.readouterr()
        assert "Could not open" in captured.err


# ---------------------------------------------------------------------------
# FileWriter instance methods (without subprocess)
# ---------------------------------------------------------------------------


class TestFileWriterMethods:
    def test_write_creates_filecontrol(self, tmp_path):

        fw = FileWriter.__new__(FileWriter)
        fw.files = {}
        fw.file_encoding = "utf-8"
        fw.open_timeout = 5

        fw.write(str(tmp_path / "out.txt"), "hello\n")
        assert len(fw.files) == 1
        fw.close_all()

    def test_close_if_open(self, tmp_path):

        fw = FileWriter.__new__(FileWriter)
        fw.files = {}
        fw.file_encoding = "utf-8"
        fw.open_timeout = 5

        path = str(tmp_path / "out.txt")
        fw.write(path, "hello\n")
        fw.close_if_open(path)

    def test_open_as_new(self, tmp_path):

        fw = FileWriter.__new__(FileWriter)
        fw.files = {}
        fw.file_encoding = "utf-8"
        fw.open_timeout = 5

        path = str(tmp_path / "out.txt")
        fw.open_as_new(path)
        assert len(fw.files) == 1

    def test_status_unopened(self, tmp_path):
        import multiprocessing

        fw = FileWriter.__new__(FileWriter)
        fw.files = {}
        fw.file_encoding = "utf-8"
        fw.open_timeout = 5
        fw.return_msg_queue = multiprocessing.Queue()

        fw.status(str(tmp_path / "nonexistent.txt"))
        result = fw.return_msg_queue.get()
        assert result == FileWriter.FileControl.STATUS_UNOPENED

    def test_status_open(self, tmp_path):
        import multiprocessing

        fw = FileWriter.__new__(FileWriter)
        fw.files = {}
        fw.file_encoding = "utf-8"
        fw.open_timeout = 5
        fw.return_msg_queue = multiprocessing.Queue()

        path = str(tmp_path / "out.txt")
        fw.write(path, "data\n")
        fw.status(path)
        result = fw.return_msg_queue.get()
        assert result == FileWriter.FileControl.STATUS_OPEN
        fw.close_all()

    def test_closed_status_all_closed(self, tmp_path):
        import multiprocessing

        fw = FileWriter.__new__(FileWriter)
        fw.files = {}
        fw.file_encoding = "utf-8"
        fw.open_timeout = 5
        fw.return_msg_queue = multiprocessing.Queue()

        fw.closed_status()
        result = fw.return_msg_queue.get()
        assert result == FileWriter.FileControl.STATUS_CLOSED

    def test_shutdown(self, tmp_path):
        fw = FileWriter.__new__(FileWriter)
        fw.files = {}
        fw.active = True
        fw.shutdown()
        assert fw.active is False

    def test_ping(self, tmp_path):
        import multiprocessing

        fw = FileWriter.__new__(FileWriter)
        fw.return_msg_queue = multiprocessing.Queue()
        fw.ping("test_token")
        assert fw.return_msg_queue.get() == "test_token"
