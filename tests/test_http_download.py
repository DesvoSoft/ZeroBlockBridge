"""Tests for app/services/http_download.py."""

import hashlib
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.services.http_download import USER_AGENT, stream_to_file


def _resp(chunks, length=None, status_error=None):
    resp = MagicMock()
    resp.headers = {"content-length": str(length)} if length is not None else {}
    resp.iter_content.return_value = chunks
    if status_error:
        resp.raise_for_status.side_effect = status_error
    return resp


def test_writes_file_and_returns_sha1(tmp_path):
    dest = tmp_path / "file.bin"
    chunks = [b"abc", b"", b"def"]
    with patch("requests.get", return_value=_resp(chunks, length=6)) as mock_get:
        digest = stream_to_file("https://example.com/f", dest, timeout=5)

    assert dest.read_bytes() == b"abcdef"
    assert digest == hashlib.sha1(b"abcdef").hexdigest()
    _, kwargs = mock_get.call_args
    assert kwargs["stream"] is True and kwargs["timeout"] == 5
    assert kwargs["headers"]["User-Agent"] == USER_AGENT


def test_reports_progress_when_length_known(tmp_path):
    progress = []
    with patch("requests.get", return_value=_resp([b"ab", b"cd"], length=4)):
        stream_to_file("u", tmp_path / "f", timeout=5, progress_callback=progress.append)
    assert progress == [0.5, 1.0]


def test_no_progress_without_content_length(tmp_path):
    progress = []
    with patch("requests.get", return_value=_resp([b"ab"])):
        stream_to_file("u", tmp_path / "f", timeout=5, progress_callback=progress.append)
    assert progress == []


def test_http_error_raises_and_closes_response(tmp_path):
    resp = _resp([], status_error=requests.HTTPError("404"))
    with patch("requests.get", return_value=resp):
        with pytest.raises(requests.HTTPError):
            stream_to_file("u", tmp_path / "f", timeout=5)
    resp.close.assert_called_once()


def test_write_error_raises_oserror_and_closes_response(tmp_path):
    resp = _resp([b"data"])
    missing_dir = tmp_path / "missing" / "f"
    with patch("requests.get", return_value=resp):
        with pytest.raises(OSError):
            stream_to_file("u", missing_dir, timeout=5)
    resp.close.assert_called_once()
