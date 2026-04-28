"""Tests for the execsql plugin.

Two testing approaches are shown:

1. **Unit tests** — test handler functions directly by mocking execsql
   state. Fast, no database needed. Good for logic validation.

2. **Integration tests** — run a real script via subprocess with the
   plugin installed. Slower, but tests the full registration +
   dispatch + execution pipeline. Good for verifying the regex
   patterns match and the handler integrates correctly.

Run with:
    pytest tests/
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Unit tests — mock execsql state, call handler directly
# ---------------------------------------------------------------------------


class TestHandlerUnit:
    def test_your_command_writes_output(self):
        """Test that the handler writes to _state.output."""
        # Import your handler
        from execsql_plugin_YOURNAME import _your_command_handler

        # Mock the state module so the handler can call _state.output.write()
        with patch("execsql.state._ctx") as mock_ctx:
            _your_command_handler(
                arg="hello world",
                metacommandline="YOUR_COMMAND hello world",
            )

        mock_ctx.output.write.assert_called_once_with(
            "YOUR_COMMAND received: hello world\n",
        )


# ---------------------------------------------------------------------------
# Registration tests — verify mcl.add() is called correctly
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_adds_commands(self):
        """Verify the register function calls mcl.add() with expected args."""
        from execsql_plugin_YOURNAME import register_metacommands

        mock_mcl = MagicMock()
        register_metacommands(mock_mcl)

        # Verify at least one command was registered
        assert mock_mcl.add.called
        # Check the description of the first registration
        call_kwargs = mock_mcl.add.call_args_list[0]
        assert call_kwargs[1].get("description") == "YOUR_COMMAND" or (
            len(call_kwargs[0]) > 2 and call_kwargs[0][2] == "YOUR_COMMAND"
        )


# ---------------------------------------------------------------------------
# Integration tests — run real scripts via subprocess
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_your_command_e2e(self, tmp_path):
        """Run a script that uses the plugin metacommand."""
        script = tmp_path / "test.sql"
        script.write_text("-- !x! YOUR_COMMAND hello world")
        db = tmp_path / "test.db"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "execsql",
                str(script),
                str(db),
                "-t",
                "l",
                "-n",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "YOUR_COMMAND received: hello world" in result.stdout

    def test_plugin_appears_in_list(self):
        """Verify the plugin shows up in --list-plugins."""
        result = subprocess.run(
            [sys.executable, "-m", "execsql", "--list-plugins"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "YOURNAME" in result.output
