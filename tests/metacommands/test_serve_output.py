"""SERVE writes a CGI response: headers, a blank line, then the file's bytes.

Under CGI stdout is a pipe.  The headers went through ``print()`` into the
text layer's buffer and the body straight to ``sys.stdout.buffer``, so the
body reached the pipe first and the headers came out at exit.
"""

from __future__ import annotations

import subprocess
import sys


def test_headers_come_before_the_body_on_a_pipe(tmp_path):
    body = b"line one\nline two\n\x00\xff binary tail"
    (tmp_path / "f.txt").write_bytes(body)
    (tmp_path / "serve.sql").write_text("-- !x! SERVE f.txt AS TXT\n", encoding="utf-8")
    out = subprocess.run(
        [sys.executable, "-m", "execsql", "run", "serve.sql", "t.db", "-t", "l", "-n"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    ).stdout
    assert out == b'Content-Type: text/plain\nContent-Disposition: attachment; filename="f.txt"\n\n' + body
