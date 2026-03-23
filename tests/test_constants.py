"""
Tests for execsql.constants — static map/icon/color data.

These are pure-data module-level assignments; importing the module and
verifying the structure is sufficient to reach 100% coverage.
"""

from __future__ import annotations

import pytest

from execsql import constants


class TestBmServers:
    def test_is_dict(self):
        assert isinstance(constants.bm_servers, dict)

    def test_has_openstreetmap(self):
        assert "OpenStreetMap" in constants.bm_servers

    def test_values_are_strings(self):
        for v in constants.bm_servers.values():
            assert isinstance(v, str)

    def test_urls_contain_tile_placeholders(self):
        # All tile server templates should have {z}/{x}/{y}
        for url in constants.bm_servers.values():
            assert "{z}" in url or "{x}" in url


class TestIconXbm:
    def test_is_dict(self):
        assert isinstance(constants.icon_xbm, dict)

    def test_known_icons_present(self):
        for name in ("ball", "flag", "star", "circle"):
            assert name in constants.icon_xbm

    def test_values_are_strings(self):
        for v in constants.icon_xbm.values():
            assert isinstance(v, str)

    def test_xbm_format_starts_with_define(self):
        for v in constants.icon_xbm.values():
            assert "#define" in v


class TestButtonBarXbms:
    def test_expand_xbm_is_string(self):
        assert isinstance(constants.expand_xbm, str)

    def test_wedges_3_xbm_is_string(self):
        assert isinstance(constants.wedges_3_xbm, str)

    def test_wedge_sm_xbm_is_string(self):
        assert isinstance(constants.wedge_sm_xbm, str)

    def test_cancel_xbm_is_string(self):
        assert isinstance(constants.cancel_xbm, str)

    def test_all_contain_define(self):
        for xbm in (
            constants.expand_xbm,
            constants.wedges_3_xbm,
            constants.wedge_sm_xbm,
            constants.cancel_xbm,
        ):
            assert "#define" in xbm


class TestColorNames:
    def test_is_tuple(self):
        assert isinstance(constants.color_names, tuple)

    def test_nonempty(self):
        assert len(constants.color_names) > 0

    def test_all_lowercase_strings(self):
        for c in constants.color_names:
            assert isinstance(c, str)
            assert c == c.lower()

    def test_common_colors_present(self):
        for color in ("red", "green", "blue", "white", "black"):
            assert color in constants.color_names


class TestCustomIcons:
    def test_is_dict(self):
        assert isinstance(constants.custom_icons, dict)

    def test_initially_empty(self):
        # custom_icons is populated at runtime; at module load it is empty.
        assert len(constants.custom_icons) == 0
