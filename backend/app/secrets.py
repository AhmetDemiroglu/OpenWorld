from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob_from_bytes(data: bytes) -> DATA_BLOB:
    buf = (ctypes.c_byte * len(data))(*data)
    return DATA_BLOB(len(data), buf)


def _bytes_from_blob(blob: DATA_BLOB) -> bytes:
    size = int(blob.cbData)
    if size <= 0:
        return b""
    ptr = ctypes.cast(blob.pbData, ctypes.POINTER(ctypes.c_ubyte))
    return bytes(ptr[:size])


def encrypt_text(text: str) -> str:
    raw = text.encode("utf-8")
    if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "crypt32"):
        in_blob = _blob_from_bytes(raw)
        out_blob = DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        )
        if not ok:
            raise RuntimeError("CryptProtectData failed")
        try:
            protected = _bytes_from_blob(out_blob)
            return "dpapi:" + base64.b64encode(protected).decode("ascii")
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    return "b64:" + base64.b64encode(raw).decode("ascii")


def decrypt_text(value: str) -> str:
    if value.startswith("dpapi:"):
        payload = base64.b64decode(value.split(":", 1)[1])
        in_blob = _blob_from_bytes(payload)
        out_blob = DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        )
        if not ok:
            raise RuntimeError("CryptUnprotectData failed")
        try:
            raw = _bytes_from_blob(out_blob)
            return raw.decode("utf-8")
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    if value.startswith("b64:"):
        return base64.b64decode(value.split(":", 1)[1]).decode("utf-8")
    return value

