"""Measurements of the roadmap 8c Qt spike (docs/QT-SPIKE.md).

  py tools/qt_spike_bench.py inproc --out DIR [--lang=es] [--theme=Light]
      In one process: dialog open times (call -> first painted frame),
      white-flash check, 2,000/20,000-line console bursts, memory, and
      screenshots of the app's own widgets (QWidget.grab(): only the app,
      never the desktop). Set QT_SCALE_FACTOR=1.5 for 150 %.

  py tools/qt_spike_bench.py startup EXE [EXE ...] [--runs 5]
      Cold start to a visible top-level window of the process tree, median
      of N runs per exe, plus the tree's memory once shown.

Reads the real data directory (servers list, settings) but changes nothing:
no server is started, and the window is never closed through exit_app.
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


# -- in-process --------------------------------------------------------------
def inproc(out: Path) -> dict:  # noqa: C901 - one linear measurement script
    from app.core.bootstrap import resolve_data_dir
    resolve_data_dir()
    from app.core.i18n import _, set_language
    lang = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--lang=")), "en")
    set_language(lang)

    import psutil
    from PySide6.QtCore import QElapsedTimer, QEvent, QEventLoop, QObject, QTimer
    from PySide6.QtWidgets import QApplication, QDialog
    from app.ui_qt.app import create_window
    from app.ui_qt.main_window import CloseChoiceDialog
    from app.ui_qt.wizard import EngineVersionDialog

    proc = psutil.Process()
    t_start = time.perf_counter()
    app = QApplication(sys.argv[:1])
    window = create_window(app)
    window.show()
    loop = QEventLoop()
    QTimer.singleShot(0, loop.quit)
    loop.exec()
    results: dict = {"lang": lang, "scale": os.environ.get("QT_SCALE_FACTOR", "1"),
                     "window_shown_ms": round((time.perf_counter() - t_start) * 1000, 1)}

    def settle(ms: int) -> None:
        end = time.perf_counter() + ms / 1000
        while time.perf_counter() < end:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)
            time.sleep(0.005)

    settle(800)  # server list + info load on workers
    results["rss_mb_idle"] = round(proc.memory_info().rss / 2**20, 1)

    class FirstPaint(QObject):
        """Marks the first time a new dialog has painted and flushed: the
        singleShot(0) after its first Paint runs once that whole backing-store
        sync (all children) is done."""
        def __init__(self):
            super().__init__()
            self.dialog = None
            self.done = False

        def eventFilter(self, obj, ev):
            if (not self.done and ev.type() == QEvent.Type.Paint
                    and isinstance(obj, QDialog) and obj is self.dialog):
                self.done = True
                QTimer.singleShot(0, loop.quit)
            return False

    def time_dialog(make) -> float:
        fp = FirstPaint()
        app.installEventFilter(fp)
        timer = QElapsedTimer()
        timer.start()
        dlg = make()
        fp.dialog = dlg
        dlg.show()
        if not fp.done:
            loop.exec()
        elapsed = timer.nsecsElapsed() / 1e6
        app.removeEventFilter(fp)
        dlg.close()
        dlg.deleteLater()
        settle(400)
        return round(elapsed, 1)

    makers = {
        "engine_version": lambda: EngineVersionDialog(window.api, window.run_async, window),
        "close_choice": lambda: CloseChoiceDialog(window, [_("the server '{name}'").format(name="Survival SMP")]),
    }
    for name, make in makers.items():
        runs = [time_dialog(make) for _run in range(10)]
        print("dialog", name, runs, file=sys.stderr, flush=True)
        results[f"dialog_{name}_ms"] = {"first": runs[0], "median_warm": statistics.median(runs[1:]),
                                        "max": max(runs), "runs": runs}

    # White-flash check: PrintWindow() copies of the dialog's own window
    # (client area, as DWM composes it) taken in a loop from the moment its
    # native window exists until 500 ms after show(). Only the dialog is
    # captured, never the desktop; frames stay in memory.
    flash_runs = []
    for _run in range(3):
        dlg = makers["engine_version"]()
        hwnd = int(dlg.winId())
        brush = class_brush(hwnd)
        frames = capture_sequence(hwnd, lambda: (dlg.show(), settle(500)), lambda: settle(10))
        dlg.close()
        dlg.deleteLater()
        settle(200)
        flash_runs.append({**summarize_frames(frames), "class_background_brush": brush})
    results["flash_check"] = flash_runs

    # Console bursts: lines emitted on the bus from a worker thread, as the
    # server reader does; the heartbeat measures how long the GUI loop stalls.
    for count in (2000, 20000):
        shown_before = window.console.lines_shown
        beats: list[float] = []
        hb = QTimer(interval=10)
        hb.timeout.connect(lambda: beats.append(time.perf_counter()))
        hb.start()
        t0 = time.perf_counter()

        def emit(n=count):
            for i in range(n):
                window.api.bus.emit("console_line", f"[12:00:{i % 60:02d}] [Server thread/INFO]: "
                                                    f"Preparing spawn area: {i * 100 // n}% (line {i})")
        th = threading.Thread(target=emit)
        th.start()
        while window.console.lines_shown - shown_before < count:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)
        t_all = time.perf_counter() - t0
        th.join()
        settle(100)
        hb.stop()
        gaps = [b - a for a, b in zip(beats, beats[1:])]
        results[f"console_burst_{count}"] = {
            "all_shown_ms": round(t_all * 1000, 1),
            "max_loop_stall_ms": round(max(gaps or [0]) * 1000, 1),
            "blocks_kept": window.console.blockCount(),
        }
    print("bursts done", file=sys.stderr, flush=True)
    results["rss_mb_after_bursts"] = round(proc.memory_info().rss / 2**20, 1)

    # Screenshots: QWidget.grab() renders the app's own widgets only.
    out.mkdir(parents=True, exist_ok=True)
    suffix = f"{lang}_{int(float(results['scale']) * 100)}"
    # Simulated running state, so the header shows its longest texts (no
    # server is started by the bench).
    from app.ui.formatting import format_memory
    viewed = window._viewed
    if viewed:
        window.api.servers.running_server = lambda: viewed
        window.api.servers.is_running = lambda: True
        window._players, window._max_players = 3, window._max_players or 20
        window._enter_phase("running")
        window._phase_since -= 4980
        window.lbl_ram.setText(format_memory(int(2.4 * 2**30)))
        window._render_status()
    window.console.clear()
    for i, line in enumerate(("[Server thread/INFO]: Starting minecraft server version 1.21.1",
                              "[Server thread/INFO]: Preparing level \"world\"",
                              "[Server thread/INFO]: Done (4.213s)! For help, type \"help\"")):
        window.console.log(line)
    window.console.flush()
    settle(200)
    window.grab().save(str(out / f"qt_main_{suffix}.png"))
    dlg = makers["engine_version"]()
    dlg.show()
    settle(1500)
    dlg.grab().save(str(out / f"qt_engine_version_{suffix}.png"))
    dlg.close()
    dlg = makers["close_choice"]()
    dlg.show()
    settle(300)
    dlg.grab().save(str(out / f"qt_close_choice_{suffix}.png"))
    dlg.close()
    window.api.events.close()
    return results


# -- flash check -------------------------------------------------------------
def print_window(hwnd: int):
    """The window's client area as DWM has it (PW_CLIENTONLY |
    PW_RENDERFULLCONTENT), as a grayscale PIL image; None before it has a size."""
    import ctypes
    from ctypes import wintypes
    from PIL import Image
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    for fn, res, args in (
            (user32.GetDC, wintypes.HDC, [wintypes.HWND]),
            (user32.ReleaseDC, ctypes.c_int, [wintypes.HWND, wintypes.HDC]),
            (user32.PrintWindow, wintypes.BOOL, [wintypes.HWND, wintypes.HDC, wintypes.UINT]),
            (user32.GetClientRect, wintypes.BOOL, [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]),
            (gdi32.CreateCompatibleDC, wintypes.HDC, [wintypes.HDC]),
            (gdi32.CreateCompatibleBitmap, wintypes.HBITMAP, [wintypes.HDC, ctypes.c_int, ctypes.c_int]),
            (gdi32.SelectObject, wintypes.HGDIOBJ, [wintypes.HDC, wintypes.HGDIOBJ]),
            (gdi32.DeleteObject, wintypes.BOOL, [wintypes.HGDIOBJ]),
            (gdi32.DeleteDC, wintypes.BOOL, [wintypes.HDC]),
            (gdi32.GetDIBits, ctypes.c_int, [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                                             ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT])):
        fn.restype, fn.argtypes = res, args
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    w, h = rect.right, rect.bottom
    if w <= 0 or h <= 0:
        return None
    wdc = user32.GetDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(wdc)
    bmp = gdi32.CreateCompatibleBitmap(wdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, 3)
    header = (ctypes.c_uint32 * 10)(40, w, (-h) & 0xFFFFFFFF, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, header, 0)
    gdi32.SelectObject(mdc, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, wdc)
    return Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("L")


def class_brush(hwnd: int) -> int:
    """The window class background brush Windows erases with before the app
    paints (0: none, so nothing is painted before the first frame)."""
    import ctypes
    fn = ctypes.windll.user32.GetClassLongPtrW
    fn.restype, fn.argtypes = ctypes.c_size_t, [ctypes.c_void_p, ctypes.c_int]
    return int(fn(hwnd, -10))  # GCLP_HBRBACKGROUND


def capture_sequence(hwnd: int, run, pump) -> list:
    """Frames of ``hwnd`` captured on a thread while ``run()`` executes.
    PrintWindow is answered by the window's own thread, so the GUI thread
    keeps pumping (``pump()``) until the grabber has stopped."""
    frames, stop = [], threading.Event()

    def grab():
        while not stop.is_set():
            img = print_window(hwnd)
            if img is not None:
                frames.append((time.perf_counter(), img.resize((96, 96))))
    th = threading.Thread(target=grab, daemon=True)
    th.start()
    try:
        run()
    finally:
        stop.set()
        while th.is_alive():
            pump()
            th.join(0.01)
    return frames


def summarize_frames(frames: list) -> dict:
    """Share of near-white pixels per frame vs the last (settled) frame: a
    white flash is an early frame much whiter than the final one."""
    def white(img):
        px = img.tobytes()
        return sum(1 for p in px if p > 235) / len(px)
    shares = [white(img) for _t, img in frames]
    final = shares[-1] if shares else 0.0
    return {"frames": len(shares), "final_white_share": round(final, 3),
            "max_white_share": round(max(shares or [0]), 3),
            "frames_whiter_than_final_by_20pct": sum(1 for s in shares if s > final + 0.2)}


def ctk_flash() -> dict:
    """Same capture on a plain CTkToplevel (dark), to check the method sees
    the flash CustomTkinter is known for."""
    import customtkinter as ctk
    ctk.set_appearance_mode("Dark")
    root = ctk.CTk()
    root.geometry("900x600")
    root.update()
    runs = []
    for _ in range(3):
        top = ctk.CTkToplevel(root)
        top.geometry("520x560")
        for i in range(12):
            ctk.CTkButton(top, text=f"Option {i}").pack(pady=4)
        top.update_idletasks()

        def pump():
            end = time.perf_counter() + 0.6
            while time.perf_counter() < end:
                root.update()
                time.sleep(0.005)
        hwnd = top.winfo_id()
        brush = class_brush(int(top.wm_frame(), 16))
        runs.append({**summarize_frames(capture_sequence(hwnd, pump, root.update)),
                     "class_background_brush": brush})
        top.destroy()
        root.update()
    root.destroy()
    return {"ctk_toplevel_flash_check": runs}


# -- startup -----------------------------------------------------------------
def _tree_pids(pid: int) -> set:
    import psutil
    try:
        p = psutil.Process(pid)
        return {pid} | {c.pid for c in p.children(recursive=True)}
    except psutil.NoSuchProcess:
        return set()


def _visible_window_of(pids: set) -> bool:
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if "ZeroBlockBridge" in buf.value or "Zero Block Bridge" in buf.value:
                found.append(hwnd)
                return False
        return True
    user32.EnumWindows(cb, 0)
    return bool(found)


def startup(exes: list, runs: int) -> dict:
    import psutil
    results = {}
    for exe in exes:
        times, rss = [], []
        for _ in range(runs):
            t0 = time.perf_counter()
            proc = subprocess.Popen([exe])
            shown = None
            while time.perf_counter() - t0 < 30:
                if _visible_window_of(_tree_pids(proc.pid)):
                    shown = time.perf_counter() - t0
                    break
                time.sleep(0.01)
            time.sleep(3)
            mem = 0
            for pid in _tree_pids(proc.pid):
                try:
                    mem += psutil.Process(pid).memory_full_info().uss
                except psutil.Error:
                    pass
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
            proc.wait()
            time.sleep(2)
            times.append(round(shown * 1000) if shown else None)
            rss.append(round(mem / 2**20, 1))
        ok = [t for t in times if t is not None]
        results[exe] = {"runs_ms": times, "median_ms": statistics.median(ok) if ok else None,
                        "uss_mb_3s_after_shown": rss, "size_mb": round(os.path.getsize(exe) / 2**20, 1)}
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    p_in = sub.add_parser("inproc")
    p_in.add_argument("--out", type=Path, required=True)
    sub.add_parser("ctkflash")
    p_st = sub.add_parser("startup")
    p_st.add_argument("exes", nargs="+")
    p_st.add_argument("--runs", type=int, default=5)
    args, _unknown = parser.parse_known_args()
    if args.mode == "inproc":
        result = inproc(args.out)
    elif args.mode == "ctkflash":
        result = ctk_flash()
    else:
        result = startup(args.exes, args.runs)
    print(json.dumps(result, indent=2), flush=True)
    os._exit(0)


if __name__ == "__main__":
    main()
