import json
from unittest.mock import patch

import pytest

from app.core import atomic_io


def test_writes_json_and_leaves_no_temp(tmp_path):
    target = tmp_path / "a" / "data.json"
    atomic_io.atomic_write_json(target, {"x": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"x": 1}
    assert [p.name for p in target.parent.iterdir()] == ["data.json"]


def test_retries_replace_while_the_target_is_briefly_locked(tmp_path):
    """Review #3: Windows refuses os.replace while AV/OneDrive/a backup has
    the file open; a short retry turns that into a success."""
    target = tmp_path / "meta.json"
    target.write_text("{}", encoding="utf-8")
    real_replace = atomic_io.os.replace
    calls = []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) < 3:
            raise PermissionError(5, "Access is denied")
        real_replace(src, dst)

    with patch.object(atomic_io.os, "replace", side_effect=flaky), patch.object(atomic_io.time, "sleep"):
        atomic_io.atomic_write_json(target, {"ok": True})
    assert len(calls) == 3
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}


def test_gives_up_after_retries_and_cleans_temp(tmp_path):
    target = tmp_path / "meta.json"
    target.write_text('{"old": 1}', encoding="utf-8")
    with patch.object(atomic_io.os, "replace", side_effect=PermissionError(5, "denied")), \
            patch.object(atomic_io.time, "sleep"):
        with pytest.raises(PermissionError):
            atomic_io.atomic_write_json(target, {"new": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"old": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["meta.json"]


def test_other_errors_are_not_retried(tmp_path):
    with patch.object(atomic_io.os, "replace", side_effect=FileNotFoundError("gone")) as rep:
        with pytest.raises(FileNotFoundError):
            atomic_io.atomic_write_json(tmp_path / "x.json", {})
    assert rep.call_count == 1
