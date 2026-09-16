"""Tests for Toast payload handling (no display needed)."""

import pytest

from app.ui.toast import ToastNotification


@pytest.mark.parametrize("toast_type", ["info", "success", "warning", "error"])
def test_known_types_pass_through(toast_type):
    assert ToastNotification.resolve_type({"msg": "x", "type": toast_type}) == toast_type


@pytest.mark.parametrize("payload", [
    {"msg": "x"},
    {"msg": "x", "type": "fatal"},
    {"msg": "x", "color": "red"},
])
def test_missing_or_unknown_type_falls_back_to_info(payload):
    assert ToastNotification.resolve_type(payload) == "info"
