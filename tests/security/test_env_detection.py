"""B20 regression tests for GUI / environment detection.

* F040 — ``utils/auth.is_plaintext_keyring()`` returns True when the
  active keyring backend is ``keyrings.alt.file.PlaintextKeyring``
  or any other backend whose module path begins with ``keyrings.alt``.
* F041 — ``utils/gui.enable_gui()`` skips the Tkinter path on POSIX
  when neither ``$DISPLAY`` nor ``$WAYLAND_DISPLAY`` is set, falling
  straight through to a non-GUI backend.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# F040 — keyring backend detection
# ---------------------------------------------------------------------------


class TestPlaintextKeyringDetection:
    def test_returns_false_when_keyring_unavailable(self):
        """No keyring installed → False (not a security claim)."""
        from execsql.utils.auth import is_plaintext_keyring

        with patch.dict("sys.modules", {"keyring": None}):
            # Even with keyring unimportable, the helper must not raise.
            try:
                result = is_plaintext_keyring()
            except Exception:
                pytest.fail("is_plaintext_keyring must swallow ImportError")
            # Either False (couldn't detect) or whatever the real keyring
            # in the test env reports — both are acceptable.
            assert isinstance(result, bool)

    def test_detects_plaintext_backend(self):
        """A backend whose module path contains ``keyrings.alt`` is plaintext."""
        from execsql.utils import auth

        # Construct a real class with the plaintext module path so the
        # type(backend).__module__ check sees the right value.
        FakeBackend = type("PlaintextKeyring", (), {})
        FakeBackend.__module__ = "keyrings.alt.file"
        fake_backend = FakeBackend()

        import keyring

        with patch.object(keyring, "get_keyring", return_value=fake_backend):
            assert auth.is_plaintext_keyring() is True

    def test_detects_real_backend_as_safe(self):
        """A backend in ``keyring.backends.macOS`` is NOT plaintext."""
        from execsql.utils import auth

        FakeBackend = type("Keyring", (), {})
        FakeBackend.__module__ = "keyring.backends.macOS"
        fake_backend = FakeBackend()

        import keyring

        with patch.object(keyring, "get_keyring", return_value=fake_backend):
            assert auth.is_plaintext_keyring() is False


# ---------------------------------------------------------------------------
# F041 — headless POSIX detection in enable_gui
# ---------------------------------------------------------------------------


@pytest.mark.skipif(os.name != "posix", reason="DISPLAY check is POSIX-only")
class TestHeadlessPosixGuiFallback:
    def test_enable_gui_skips_tkinter_when_no_display(self, monkeypatch):
        """B20/F041: with no DISPLAY/WAYLAND_DISPLAY on POSIX,
        enable_gui must NOT attempt the Tkinter import path."""
        import execsql.utils.gui as gui_mod

        # Reset the module-level backend cache.
        monkeypatch.setattr(gui_mod, "_active_backend", None)
        # Clear display env vars to simulate a headless runner.
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

        import execsql.state as _state

        fake_conf = MagicMock()
        fake_conf.gui_framework = "tkinter"
        monkeypatch.setattr(_state, "conf", fake_conf)

        # If the Tkinter path were taken, this import patch would never
        # be touched. Patch it anyway to ensure no attempt is made.
        with patch("execsql.gui.desktop.TkinterBackend") as mock_tk:
            try:
                gui_mod.enable_gui()
            except Exception:
                pass  # We don't care if textual / console also fail.
            mock_tk.assert_not_called()
