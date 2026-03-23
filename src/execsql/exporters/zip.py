from __future__ import annotations

"""
ZIP archive writing for execsql exporters.

Provides :class:`WriteableZipfile` (a thin :class:`zipfile.ZipFile`
subclass that supports chunked writes) and :class:`ZipWriter`, the
higher-level interface used by the EXPORT metacommand when the output is
directed into a ``.zip`` archive.
"""

import io
import os
import sys
import time
import zipfile
from typing import Optional

import execsql.state as _state


class WriteableZipfile:
    def __init__(self, zipfile_name: str, append: bool = False) -> None:
        conf = _state.conf
        self.bufsize = conf.zip_buffer_mb * 1024 * 1000
        self.buf = memoryview(bytearray(self.bufsize))
        self.buflen = 0  # Length of buffer contents.
        comp = zipfile.ZIP_BZIP2
        zmode = "w" if not append else "a"
        self.zf = zipfile.ZipFile(zipfile_name, mode=zmode, compression=comp, compresslevel=9)
        self.current_handle = None

    def __del__(self) -> None:
        self.close()

    def member_file(self, member_filename: str) -> None:
        # Creates a ZipInfo object (file) within the zipfile and opens it for writing.
        self.current_zinfo = zipfile.ZipInfo(
            filename=member_filename,
            date_time=time.localtime(time.time())[:6],
        )
        self.current_zinfo.compress_type = self.zf.compression
        if sys.version_info.major >= 3 and sys.version_info.minor >= 7:
            self.current_zinfo._compresslevel = self.zf.compresslevel
        # See https://stackoverflow.com/questions/434641/how-do-i-set-permissions-attributes-on-a-file-in-a-zip-file-using-pythons-zip
        self.current_zinfo.external_attr = 0o100755 << 16  # ?rw-rw-rw-
        if sys.platform.startswith("win"):
            self.current_zinfo.create_system = 0
        else:
            self.current_zinfo.create_system = 3
        self.current_zinfo.file_size = 0
        self.current_handle = self.zf.open(self.current_zinfo, mode="w")

    def zip_buffer(self) -> None:
        # Writes the buffer contents, if any, to the zip member file.
        if self.buflen > 0 and self.current_handle is not None:
            with self.zf._lock:
                self.current_zinfo.file_size = self.current_zinfo.file_size + self.buflen
                self.current_handle.write(self.buf[0 : self.buflen])
            self.buflen = 0

    def write(self, str_data: str) -> None:
        # Writes the given text to the currently open member.
        # Convert from string to bytes.
        data = str_data.encode("utf-8")
        datalen = len(data)
        if self.buflen + datalen > self.bufsize:
            self.zip_buffer()
        self.buf[self.buflen : self.buflen + datalen] = data
        self.buflen = self.buflen + datalen

    def close_member(self) -> None:
        if self.current_handle is not None:
            self.zip_buffer()
            self.current_handle.close()
            self.current_handle = None

    def close(self) -> None:
        self.close_member()
        self.zf.close()


class ZipWriter:
    def __init__(self, zip_fname: str, member_fname: str, append: bool = False) -> None:
        self.zip_fname = zip_fname
        self.member_fname = member_fname
        self.zwriter = WriteableZipfile(self.zip_fname, append)
        self.member = self.zwriter.member_file(member_fname)

    def write(self, str_data: str) -> None:
        self.zwriter.write(str_data)

    def close(self) -> None:
        self.zwriter.close()
        self.zwriter = None
