"""Manifest-enabled text writes preserve bytes and report only confirmed output."""

import io
from types import SimpleNamespace

import pytest

import execsql.state as state
from execsql.manifest import RunManifest
from execsql.metacommands import DISPATCH_TABLE
from execsql.script.variables import SubVarSet
from execsql.utils.fileio import (
    FileWriter,
    filewriter_close_all_after_write,
    filewriter_end,
    filewriter_write,
)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_manifest_receipts_preserve_every_written_character(tmp_path, encoding):
    messages = ["", "0001\n", "1.2500\n", "é e\u0301 漢字 🐟\n", '"quoted"\\path\t\x00\r\n']
    outputs = []
    for enabled in (False, True):
        path = tmp_path / f"{enabled}.txt"
        manifest = RunManifest(str(tmp_path / "m.json"), "s.sql", []) if enabled else None
        state.manifest = manifest
        writer = FileWriter(file_encoding=encoding)
        state.filewriter = writer
        writer.start()
        try:
            if manifest:
                with manifest.command("WRITE text TO data.txt", "s.sql", 7, DISPATCH_TABLE):
                    for message in messages:
                        filewriter_write(str(path), message)
            else:
                for message in messages:
                    filewriter_write(str(path), message)
            filewriter_close_all_after_write()
            outputs.append(path.read_bytes())
            if manifest:
                assert len(manifest.writes) == 1
                assert manifest.writes[0]["line"] == 7
                receipts = next(iter(manifest._queued_writes.values()))
                assert len(receipts) == len(messages)
                assert all(receipt.written for receipt in receipts)
                assert all(not isinstance(receipt, str) for receipt in receipts)  # Retain flags, not output payloads.
        finally:
            filewriter_end(writer)
            state.manifest = None
    assert outputs[0] == outputs[1]


def test_a_later_flush_failure_does_not_erase_an_earlier_confirmed_write(tmp_path):
    class FailingFlush(io.StringIO):
        flushes = 0

        def flush(self):
            self.flushes += 1
            if self.flushes == 2:
                raise OSError("full disk")

    manifest = RunManifest(str(tmp_path / "m.json"), "s.sql", [])
    control = FileWriter.FileControl("data.txt", 10)
    control.handle = FailingFlush()
    control.status = control.STATUS_OPEN
    with manifest.command("WRITE first TO data.txt", "s.sql", 1, DISPATCH_TABLE):
        first = manifest.queued_write("data.txt", "first\n")
        control.write(first)
    with manifest.command("WRITE second TO data.txt", "s.sql", 2, DISPATCH_TABLE):
        second = manifest.queued_write("data.txt", "second\n")
        control.write(second)
    manifest.finish(1)
    import json

    data = json.loads((tmp_path / "m.json").read_text())
    assert [entry["line"] for entry in data["files_written"]] == [1]
    assert next(iter(manifest._queued_writes.values()))[0].written is True
    assert list(manifest._queued_writes.values())[1][0].written is False


@pytest.mark.parametrize("fails", [False, True])
def test_deferred_email_file_reads_are_not_recorded_at_registration(tmp_path, monkeypatch, fails):
    from execsql.utils import mail

    class FakeMailer:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def sendmail(self, *args):
            if fails:
                raise OSError("test mail failure")

    monkeypatch.setattr(mail, "Mailer", FakeMailer)
    manifest = RunManifest(str(tmp_path / "m.json"), "s.sql", [])
    state.manifest = manifest
    state.subvars = SubVarSet()
    state.last_command = SimpleNamespace(source="s.sql", line_no=7)
    command = 'ON ERROR_HALT EMAIL FROM from@example.invalid TO to@example.invalid SUBJECT "failure" MESSAGE "failed" ATTACH_FILE "detail.txt"'
    assert DISPATCH_TABLE.get_match(command) is not None
    manifest.record_metacommand(command, "s.sql", 7, DISPATCH_TABLE)
    spec = mail.MailSpec(
        "from@example.invalid",
        "to@example.invalid",
        "failure",
        "failed",
        attach_filename="detail.txt",
        by="ON ERROR_HALT EMAIL",
    )
    assert manifest.reads == []
    if fails:
        with pytest.raises(OSError, match="test mail failure"):
            spec.send()
        assert manifest.reads == []
    else:
        spec.send()
        assert manifest.reads == [{"source": "s.sql", "line": 7, "by": "ON ERROR_HALT EMAIL", "path": "detail.txt"}]
