from app.ui.window_state import parse_geometry, restorable_geometry

SCREEN = (0, 0, 1920, 1080)
MIN = (900, 580)


def test_parse_geometry_full_string():
    assert parse_geometry("1150x700+40+60") == (1150, 700, 40, 60)


def test_parse_geometry_negative_offsets():
    assert parse_geometry("1150x700+-1900+20") == (1150, 700, -1900, 20)


def test_parse_geometry_rejects_partial_or_garbage():
    assert parse_geometry("1150x700") is None
    assert parse_geometry("") is None
    assert parse_geometry(None) is None
    assert parse_geometry("big") is None


def test_restorable_geometry_keeps_valid_value():
    assert restorable_geometry("1200x800+100+50", MIN, SCREEN) == "1200x800+100+50"


def test_restorable_geometry_clamps_size():
    assert restorable_geometry("400x300+100+50", MIN, SCREEN) == "900x580+100+50"
    assert restorable_geometry("5000x3000+0+0", MIN, SCREEN) == "1920x1080+0+0"


def test_restorable_geometry_rejects_off_screen_position():
    # Saved on a monitor that is no longer connected
    assert restorable_geometry("1200x800+2500+50", MIN, SCREEN) is None
    assert restorable_geometry("1200x800+-1500+50", MIN, SCREEN) is None
    assert restorable_geometry("1200x800+100+1060", MIN, SCREEN) is None


def test_restorable_geometry_accepts_secondary_monitor_on_the_left():
    virtual = (-1920, 0, 3840, 1080)
    assert restorable_geometry("1200x800+-1800+50", MIN, virtual) == "1200x800+-1800+50"
