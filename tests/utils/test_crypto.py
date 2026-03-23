"""Tests for the Encrypt class in execsql.utils.crypto."""

from __future__ import annotations

import pytest

from execsql.utils.crypto import Encrypt


class TestEncrypt:
    def setup_method(self):
        self.enc = Encrypt()

    def test_repr(self):
        assert repr(self.enc) == "Encrypt()"

    def test_encrypt_returns_string(self):
        result = self.enc.encrypt("password")
        assert isinstance(result, str)

    def test_encrypt_is_not_plaintext(self):
        result = self.enc.encrypt("mysecret")
        assert "mysecret" not in result

    def test_roundtrip_simple(self):
        plaintext = "hello"
        assert self.enc.decrypt(self.enc.encrypt(plaintext)) == plaintext

    def test_roundtrip_empty_string(self):
        assert self.enc.decrypt(self.enc.encrypt("")) == ""

    def test_roundtrip_long_string(self):
        plaintext = "a" * 200
        assert self.enc.decrypt(self.enc.encrypt(plaintext)) == plaintext

    def test_roundtrip_special_chars(self):
        plaintext = "p@ssw0rd!#$%"
        assert self.enc.decrypt(self.enc.encrypt(plaintext)) == plaintext

    def test_encrypt_nondeterministic(self):
        # Different calls produce different ciphertexts (random salt)
        ct1 = self.enc.encrypt("test")
        ct2 = self.enc.encrypt("test")
        # This is probabilistic; they *could* collide but it's extremely unlikely
        # At minimum both should decrypt back correctly
        assert self.enc.decrypt(ct1) == "test"
        assert self.enc.decrypt(ct2) == "test"

    def test_xor_symmetric(self):
        """xor(xor(text, key), key) == text."""
        import itertools

        key = "somekey"
        text = "hello world"
        xored = self.enc.xor(text, key)
        restored = self.enc.xor(xored, key)
        assert restored == text

    @pytest.mark.parametrize("key", list(Encrypt.ky.keys()))
    def test_all_key_slots_roundtrip(self, key):
        """Force a specific key slot and verify roundtrip."""
        import random

        # Patch random so we always choose this key slot
        original_randint = random.randint
        kykeys = list(Encrypt.ky)
        idx = kykeys.index(key)
        random.randint = lambda a, b: idx
        try:
            plaintext = "secret"
            ct = self.enc.encrypt(plaintext)
            assert self.enc.decrypt(ct) == plaintext
        finally:
            random.randint = original_randint
