"""Measurements of the visual-ceiling spike (docs/QT-SPIKE.md, "Visual ceiling").

  py tools/qt_visual_bench.py widgets|qml --out DIR [--lang=es] [--theme=Dark|Light]

One process per variant: open time (construction -> first frame), frame
times during server-switch transitions, CPU (and GPU, from the Windows
"GPU Engine" counters) idle and while animating, a 2,000-line console
burst, and screenshots of the app's own window only (QWidget.grab /
QQuickWindow.grabWindow, plus PrintWindow of that one window to include
the Mica backdrop). No server is started; the running state is simulated.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))


def gpu_percent(pid: int, seconds: int) -> float | None:
    """Mean 3D-engine utilization of ``pid`` over ``seconds``, one WMI sample
    per second (Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine,
    whose names are not localized); None when unavailable."""
    ps = ("$v = @(); for ($i = 0; $i -lt %d; $i++) { "
          "$v += (Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine "
          "| Where-Object { $_.Name -like 'pid_%d_*engtype_3D' } "
          "| Measure-Object UtilizationPercentage -Sum).Sum; Start-Sleep -Milliseconds 1000 }; "
          "($v | Measure-Object -Average).Average") % (seconds, pid)
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                             timeout=seconds * 4 + 20).stdout.strip()
        return round(float(out.replace(",", ".")), 1) if out else None
    except (subprocess.SubprocessError, ValueError):
        return None


def main() -> None:  # noqa: C901 - one linear measurement script
    parser = argparse.ArgumentParser()
    parser.add_argument("variant", choices=("widgets", "qml"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--lang", default="es")
    parser.add_argument("--theme", default="Dark")
    parser.add_argument("--no-shadow", action="store_true", help="widgets: cards without drop shadows")
    args = parser.parse_args()

    from app.core.bootstrap import resolve_data_dir
    resolve_data_dir()
    from app.core.i18n import set_language
    set_language(args.lang)

    import psutil
    from PySide6.QtCore import QElapsedTimer, QEvent, QEventLoop, QObject, QTimer
    from PySide6.QtWidgets import QApplication
    import qt_spike_bench as qb

    proc = psutil.Process()
    app = QApplication(sys.argv[:1])
    frames: list[float] = []

    class FrameTap(QObject):
        """Widgets: paint events of the animated header title."""
        def eventFilter(self, _obj, ev):
            if ev.type() == QEvent.Type.Paint:
                frames.append(time.perf_counter())
            return False

    from app.api import AppApi
    from app.ui_qt import theme
    from app.ui_qt.dispatcher import QtDispatcher
    from app.ui_qt.visual.backend import MainBackend
    t_api = time.perf_counter()
    dispatcher = QtDispatcher(app)
    api = AppApi(dispatcher=dispatcher)
    api_ms = (time.perf_counter() - t_api) * 1000
    timer = QElapsedTimer()
    timer.start()
    dark = theme.apply(app, args.theme)
    app.setStyleSheet("")
    backend = MainBackend(api, dispatcher, app)
    if args.variant == "qml":
        from app.ui_qt.visual.qml_main import create_qml_window
        window = create_qml_window(app, backend, dark)
    else:
        from app.ui_qt.visual import widgets_main
        widgets_main.SHADOWS = not args.no_shadow
        window = widgets_main.WidgetsMainWindow(backend, dark)
    first = {}
    if args.variant == "qml":
        window.frameSwapped.connect(lambda: frames.append(time.perf_counter()))
        window.frameSwapped.connect(lambda: first.setdefault("ms", timer.nsecsElapsed() / 1e6))
    else:
        tap = FrameTap()
        window.winId()
        # The header title repaints once per frame while the switch
        # transition animates: its paint times are the frame times.
        window.lbl_name.installEventFilter(tap)
        orig = window.paintEvent

        def paint(e):
            orig(e)
            if "ms" not in first:
                QTimer.singleShot(0, lambda: first.setdefault("ms", timer.nsecsElapsed() / 1e6))
        window.paintEvent = paint
    window.show()
    while "ms" not in first and timer.elapsed() < 10000:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 5)

    def settle(seconds: float) -> None:
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 5)
            time.sleep(0.002)

    results: dict = {"variant": args.variant + ("-noshadow" if args.no_shadow else ""), "lang": args.lang, "theme": args.theme,
                     "scale": os.environ.get("QT_SCALE_FACTOR", "1"),
                     "refresh_hz": round(app.primaryScreen().refreshRate(), 1),
                     "api_create_ms": round(api_ms, 1),
                     "screen_open_to_first_frame_ms": round(first.get("ms", -1), 1),
                     "mica": bool(getattr(window, "mica", False)) or args.variant == "qml"}
    settle(1.5)
    results["rss_mb"] = round(proc.memory_info().rss / 2**20, 1)

    def cpu_and_gpu(seconds: int, during=None) -> dict:
        gpu: dict = {}
        th = threading.Thread(target=lambda: gpu.setdefault("v", gpu_percent(os.getpid(), seconds)))
        proc.cpu_percent(None)
        th.start()
        end = time.perf_counter() + seconds + 1
        while time.perf_counter() < end:
            if during:
                during()
            settle(0.05)
        cpu = proc.cpu_percent(None) / psutil.cpu_count()
        th.join()
        return {"cpu_pct_of_machine": round(cpu, 1), "gpu_3d_pct": gpu.get("v")}

    results["idle_offline"] = cpu_and_gpu(4)
    backend.demo_running()
    settle(0.5)
    results["idle_running_pulse"] = cpu_and_gpu(4)

    # Server-switch transitions: select the next server every 450 ms and
    # record frame intervals while they animate.
    servers = backend.servers or [backend.selected]
    state = {"i": 0, "next": 0.0}

    switches: list[float] = []

    def switch():
        now = time.perf_counter()
        if now >= state["next"]:
            switches.append(now)
            state["i"] += 1
            backend._selected = ""  # allow re-selecting in a loop
            backend.select(servers[state["i"] % len(servers)])
            state["next"] = now + 0.45
    frames.clear()
    results["during_transitions"] = cpu_and_gpu(4, switch)
    # Frame intervals inside each transition window (300 ms after a switch).
    gaps = [(b - a) * 1000 for a, b in zip(frames, frames[1:])
            if any(sw <= a and b <= sw + 0.3 for sw in switches)]
    if gaps:
        gaps.sort()
        results["transition_frames"] = {
            "switches": len(switches), "intervals": len(gaps),
            "p50_ms": round(statistics.median(gaps), 1), "p95_ms": round(gaps[int(len(gaps) * 0.95)], 1),
            "max_ms": round(gaps[-1], 1),
            "over_33ms": sum(1 for g in gaps if g > 33.4)}
    settle(0.6)

    # Console burst through the real EventBus.
    beats: list[float] = []
    hb = QTimer(interval=10)
    hb.timeout.connect(lambda: beats.append(time.perf_counter()))
    hb.start()
    t0 = time.perf_counter()
    before = backend.console.rowCount()

    def emit():
        for i in range(2000):
            backend.api.bus.emit("console_line", f"[12:00:{i % 60:02d}] [Server thread/INFO]: Preparing spawn area: "
                                                 f"{i * 100 // 2000}% (line {i})")
    th = threading.Thread(target=emit)
    th.start()
    th.join()
    while backend._pending or backend._flush.isActive():
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 5)
    done_ms = (time.perf_counter() - t0) * 1000
    settle(0.2)
    hb.stop()
    gaps = [b - a for a, b in zip(beats, beats[1:])]
    results["console_burst_2000"] = {"delivered_ms": round(done_ms, 1),
                                     "max_loop_stall_ms": round(max(gaps or [0]) * 1000, 1),
                                     "rows": backend.console.rowCount(), "rows_before": before}

    # Screenshots (app window only).
    args.out.mkdir(parents=True, exist_ok=True)
    backend.console.clear()
    window_console = getattr(window, "console", None)
    if window_console is not None:
        window_console.clear()
    backend._selected = ""
    backend.select(servers[0])
    settle(0.8)
    backend.demo_running()
    for line in ("[Server thread/INFO]: Starting minecraft server version 1.21.1",
                 "[Server thread/INFO]: Preparing level \"world\"",
                 "[Server thread/INFO]: Done (4.213s)! For help, type \"help\""):
        backend._on_line(line)
    settle(1.0)
    tag = f"{args.variant}_{args.lang}_{args.theme.lower()}_{int(float(results['scale']) * 100)}"
    (window.grab() if args.variant == "widgets" else window.grabWindow()).save(str(args.out / f"{tag}.png"))
    shot: dict = {}
    hwnd = int(window.winId())
    th = threading.Thread(target=lambda: shot.setdefault("img", qb.print_window(hwnd, color=True, whole=True)))
    th.start()
    while th.is_alive():
        app.processEvents()
        th.join(0.01)
    if shot.get("img") is not None:
        shot["img"].save(str(args.out / f"{tag}_window.png"))
    results["rss_mb_end"] = round(proc.memory_info().rss / 2**20, 1)
    print(json.dumps(results, indent=1), flush=True)
    os._exit(0)


if __name__ == "__main__":
    main()
