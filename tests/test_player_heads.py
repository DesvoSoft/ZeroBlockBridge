import os
import time
from unittest.mock import patch

import pytest
import requests

from app.services import player_heads as heads

UUID = "069a79f4-44e9-4726-a5be-fca90e38aaf5"


@pytest.fixture
def cache(tmp_path):
    with patch.object(heads, "HEAD_CACHE_DIR", tmp_path):
        yield tmp_path


def _fake_download(url, dest, timeout):
    with open(dest, "wb") as f:
        f.write(b"png")
    return "sha1"


def test_downloads_into_cache_by_uuid(cache):
    with patch.object(heads, "stream_to_file", side_effect=_fake_download) as dl:
        path = heads.fetch_head(UUID, 64)
    assert path == cache / "069a79f444e94726a5befca90e38aaf5_64.png"
    assert path.read_bytes() == b"png"
    assert dl.call_args.args[0] == "https://mc-heads.net/avatar/069a79f444e94726a5befca90e38aaf5/64"


def test_fresh_cache_skips_network(cache):
    heads.head_cache_path(UUID, 64).write_bytes(b"old")
    with patch.object(heads, "stream_to_file") as dl:
        assert heads.fetch_head(UUID, 64).read_bytes() == b"old"
    dl.assert_not_called()


def test_stale_cache_refreshes(cache):
    path = heads.head_cache_path(UUID, 64)
    path.write_bytes(b"old")
    old = time.time() - heads.MAX_AGE_SECONDS - 10
    os.utime(path, (old, old))
    with patch.object(heads, "stream_to_file", side_effect=_fake_download):
        assert heads.fetch_head(UUID, 64).read_bytes() == b"png"


def test_network_error_falls_back_to_stale_copy(cache):
    path = heads.head_cache_path(UUID, 64)
    path.write_bytes(b"old")
    old = time.time() - heads.MAX_AGE_SECONDS - 10
    os.utime(path, (old, old))
    with patch.object(heads, "stream_to_file", side_effect=requests.ConnectionError("down")):
        assert heads.fetch_head(UUID, 64) == path


def test_network_error_without_cache_returns_none(cache):
    with patch.object(heads, "stream_to_file", side_effect=requests.ConnectionError("down")):
        assert heads.fetch_head(UUID, 64) is None
    assert list(cache.iterdir()) == []


def test_empty_uuid():
    assert heads.fetch_head("") is None
