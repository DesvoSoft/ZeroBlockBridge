"""download_with_verification publishes a file only once it is complete."""
from unittest.mock import patch

import requests

from app.services import sha1_validator as v


def _fake_stream(content: bytes, fail_after: bool = False, digest="ok"):
    def stream(url, path, timeout, progress_callback=None):
        with open(path, "wb") as f:
            f.write(content)
        if fail_after:
            raise requests.ConnectionError("connection reset mid-download")
        return digest
    return stream


def test_success_publishes_and_leaves_no_part(tmp_path):
    dest = tmp_path / "mods" / "a.jar"
    dest.parent.mkdir()
    with patch.object(v, "stream_to_file", side_effect=_fake_stream(b"full jar", digest="abc")):
        assert v.download_with_verification("u", str(dest), expected_sha1="ABC") == (True, str(dest), None)
    assert dest.read_bytes() == b"full jar"
    assert [p.name for p in dest.parent.iterdir()] == ["a.jar"]


def test_interrupted_download_never_appears_as_the_jar(tmp_path):
    """Review A: with daemon workers a closing app can cut a download short;
    the truncated bytes must never sit at mods/<name>.jar."""
    dest = tmp_path / "a.jar"
    with patch.object(v, "stream_to_file", side_effect=_fake_stream(b"trunc", fail_after=True)), \
            patch.object(v.time, "sleep"):
        ok, path, error = v.download_with_verification("u", str(dest), max_retries=2)
    assert not ok and path is None and "failed" in error.lower()
    assert list(tmp_path.iterdir()) == []


def test_part_file_is_where_bytes_stream(tmp_path):
    seen = []

    def stream(url, path, timeout, progress_callback=None):
        seen.append(path)
        open(path, "wb").close()
        return "x"
    with patch.object(v, "stream_to_file", side_effect=stream):
        v.download_with_verification("u", str(tmp_path / "a.jar"))
    assert seen == [str(tmp_path / "a.jar") + ".part"]


def test_checksum_mismatch_keeps_previous_file(tmp_path):
    dest = tmp_path / "server.jar"
    dest.write_bytes(b"previous good jar")
    with patch.object(v, "stream_to_file", side_effect=_fake_stream(b"bad", digest="nope")), \
            patch.object(v.time, "sleep"):
        ok, _, error = v.download_with_verification("u", str(dest), expected_sha1="abc", max_retries=2)
    assert not ok and "corruption" in error
    assert dest.read_bytes() == b"previous good jar"
    assert [p.name for p in tmp_path.iterdir()] == ["server.jar"]


def test_write_error_cleans_part(tmp_path):
    dest = tmp_path / "a.jar"

    def stream(url, path, timeout, progress_callback=None):
        open(path, "wb").close()
        raise OSError("disk full")
    with patch.object(v, "stream_to_file", side_effect=stream):
        ok, _, error = v.download_with_verification("u", str(dest))
    assert not ok and "disk full" in error
    assert list(tmp_path.iterdir()) == []
