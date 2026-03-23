from __future__ import annotations

"""
Simple reversible encryption for execsql configuration credentials.

Provides :class:`Encrypt` with ``encrypt()`` / ``decrypt()`` methods
that use XOR against a fixed key table followed by base64 encoding.
This is *not* cryptographically secure — it is intended only to prevent
plaintext passwords from appearing verbatim in ``execsql.conf`` files.
The monolith (line 2301) called this "SIMPLE ENCRYPTION".
"""

import random
import uuid


class Encrypt:
    ky: dict = {}
    ky["0"] = "6f2bba010bdf450a99c1c324ace5d765"
    ky["3"] = "4a69dd15b6304ed491f10d0ebc7498cf"
    ky["9"] = "c06d0798e55a4ea2822cf6e3f0d32520"
    ky["e"] = "1ab984b7c7574c18a5eee2be92236f19"
    ky["g"] = "ee66e201ca9c4b55b7037eb5f94be9e4"
    ky["n"] = "63fad3d6c81c4668b89533b9af182aa1"
    ky["p"] = "647ff4e2bfec48b9a7a8ca4e4878769e"
    ky["w"] = "5274bb5b1421406fa57c4863321dd111"
    ky["z"] = "624b1d0835fb45caa2d0664c103179f3"

    def __repr__(self) -> str:
        return "Encrypt()"

    def __init__(self) -> None:
        global itertools
        global base64
        import itertools, base64

    def xor(self, text: str, enckey: str) -> str:
        return "".join(chr(ord(t) ^ ord(k)) for t, k in zip(text, itertools.cycle(enckey)))

    def encrypt(self, plaintext: str) -> str:
        random.seed()
        kykey = list(self.ky)[random.randint(0, len(list(self.ky)) - 1)]
        kyval = self.ky[kykey]
        noiselen = random.randint(1, 15)
        noise = str(uuid.uuid4()).replace("-", "")[0:noiselen]
        encstr = kykey + format(noiselen, "1x") + self.xor(noise + plaintext, kyval)
        enc = base64.b64encode(bytes(encstr, "utf-8"))
        return enc.decode("utf-8")

    def decrypt(self, crypttext: str) -> str:
        enc = base64.b64decode(bytes(crypttext, "utf-8"))
        encstr = enc.decode("utf-8")
        kyval = self.ky[encstr[0]]
        noiselen = int(encstr[1], 16)
        return self.xor(encstr[2:], kyval)[noiselen:]
