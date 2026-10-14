"""Minimal reader for Minecraft's NBT format (enough for level.dat).

level.dat is a gzip-compressed, big-endian NBT file. Only reading is
supported; arrays and lists are parsed so they can be skipped correctly.
Spec: https://minecraft.wiki/w/NBT_format
"""

import gzip
import struct
from typing import Any, BinaryIO

TAG_END, TAG_BYTE, TAG_SHORT, TAG_INT, TAG_LONG = 0, 1, 2, 3, 4
TAG_FLOAT, TAG_DOUBLE, TAG_BYTE_ARRAY, TAG_STRING = 5, 6, 7, 8
TAG_LIST, TAG_COMPOUND, TAG_INT_ARRAY, TAG_LONG_ARRAY = 9, 10, 11, 12

# A real level.dat is a few KB; refuse anything absurd (corrupt or hostile).
MAX_BYTES = 64 * 1024 * 1024
_MAX_DEPTH = 512

_SCALARS = {
    TAG_BYTE: ">b", TAG_SHORT: ">h", TAG_INT: ">i", TAG_LONG: ">q",
    TAG_FLOAT: ">f", TAG_DOUBLE: ">d",
}
_ARRAYS = {TAG_BYTE_ARRAY: 1, TAG_INT_ARRAY: 4, TAG_LONG_ARRAY: 8}


class NbtError(ValueError):
    """Not a readable NBT file."""


def _read(stream: BinaryIO, n: int) -> bytes:
    data = stream.read(n)
    if len(data) != n:
        raise NbtError("unexpected end of NBT data")
    return data


def _unpack(stream: BinaryIO, fmt: str):
    return struct.unpack(fmt, _read(stream, struct.calcsize(fmt)))[0]


def _string(stream: BinaryIO) -> str:
    return _read(stream, _unpack(stream, ">H")).decode("utf-8", "replace")


def _payload(stream: BinaryIO, tag: int, depth: int) -> Any:
    if depth > _MAX_DEPTH:
        raise NbtError("NBT nesting too deep")
    if tag in _SCALARS:
        return _unpack(stream, _SCALARS[tag])
    if tag == TAG_STRING:
        return _string(stream)
    if tag in _ARRAYS:
        length = _unpack(stream, ">i")
        if length < 0:
            raise NbtError("negative array length")
        _read(stream, length * _ARRAYS[tag])
        return None  # contents not needed: skipped
    if tag == TAG_LIST:
        item_tag, length = _unpack(stream, ">b"), _unpack(stream, ">i")
        return [_payload(stream, item_tag, depth + 1) for _ in range(max(length, 0))]
    if tag == TAG_COMPOUND:
        return _compound(stream, depth + 1)
    raise NbtError(f"unknown NBT tag {tag}")


def _compound(stream: BinaryIO, depth: int) -> dict:
    result = {}
    while True:
        tag = _unpack(stream, ">b")
        if tag == TAG_END:
            return result
        name = _string(stream)
        result[name] = _payload(stream, tag, depth)


def parse(data: bytes) -> dict:
    """Root compound of an NBT document (gzip-compressed or raw)."""
    import io
    if data[:2] == b"\x1f\x8b":
        try:
            data = gzip.decompress(data)
        except (OSError, EOFError) as e:
            raise NbtError(f"not a valid gzip stream: {e}") from e
    stream = io.BytesIO(data)
    if _unpack(stream, ">b") != TAG_COMPOUND:
        raise NbtError("NBT root is not a compound")
    _string(stream)  # root name, usually empty
    return _compound(stream, 0)


def read_file(path) -> dict:
    with open(path, "rb") as f:
        data = f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise NbtError("file too large to be a level.dat")
    return parse(data)
