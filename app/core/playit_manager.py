import os
import platform
import subprocess
import threading
import requests
import re
import time
import logging

from app.core.constants import BIN_DIR, CONFIG_DIR, PLAYIT_VERSION, PLAYIT_URL_WINDOWS, PLAYIT_URL_LINUX, subprocess_flags
from app.services.playit_api import PlayitApiClient, PlayitApiException

logger = logging.getLogger(__name__)

from app.core.constants import ANSI_ESCAPE_RE

from typing import Callable, Optional, Any

class PlayitManager:
    def __init__(self, console_callback: Callable[[str], None], status_callback: Callable[[str, Optional[str]], None], on_ready_callback: Optional[Callable[[], None]]=None, notification_callback: Optional[Callable[[str, str], None]]=None) -> None:
        self.console_callback = console_callback
        self.status_callback = status_callback
        self.on_ready_callback = on_ready_callback
        self.notification_callback = notification_callback
        self.process = None
        self.running = False
        self.binary_path = self._get_binary_path()
        # playitd has no "version" subcommand — installed version is tracked
        # in a marker file written after a validated download.
        self.version_marker_path = BIN_DIR / "playit.version"
        self.current_address = None
        self.is_linked = False
        self.toml_path = os.path.join(CONFIG_DIR, "playit.toml")

        # API Client and state
        self.api_client = PlayitApiClient()
        self._lock = threading.RLock()
        self._api_dns = None
        # --- CRITICAL DNS: stdout DNS — recovered via _parse_line regex from agent stdout ---
        self._stdout_dns = None
        self._current_port = 25565

        # Persistence: Check if already linked
        if self.api_client.load_secret_key():
            self.is_linked = True
            self._fix_permissions()
            logger.info("Playit linked state persisted from playit.toml")

        # Set when agent exits due to auth failure — suppresses heartbeat restart
        self._auth_failed = False
        # Timestamp of the last successful link — a secret revoked shortly
        # after linking points to an account over its agent/port limit
        self._linked_at = 0.0
        # Guards against concurrent tunnel creation when the agent repeats
        # its "0 tunnels" line across reconnect attempts
        self._tunnel_create_inflight = False

        self._shutdown_done = False
        self._job_handle = None
        import atexit
        atexit.register(self._atexit_stop)

    def _atexit_stop(self) -> None:
        # Graceful path: skip if shutdown() already completed the full stop.
        # However, always fire the by-name nuclear kill on Windows as a safety
        # net in case the 3-second join timeout expired before stop() finished.
        try:
            if not self._shutdown_done:
                self._shutdown_done = True
                self.stop(force=True)
            elif platform.system() == "Windows":
                # Backstop: taskkill silently (no window, no flash) even if we
                # think we already stopped — harmless if process is already dead.
                for proc_name in ["playit.exe", "playit-cli.exe"]:
                    subprocess.run(
                        ["taskkill", "/F", "/IM", proc_name],
                        capture_output=True, check=False,
                        **subprocess_flags(),
                    )
        except Exception as e:
            logger.debug("atexit_stop suppressed: %s", e)

    def _get_binary_path(self) -> Any:
        system = platform.system()
        filename = "playit.exe" if system == "Windows" else "playit"
        return (BIN_DIR / filename).resolve()

    def _clean_stale_binaries(self) -> None:
        if not BIN_DIR.exists():
            return
        for f in BIN_DIR.iterdir():
            if f.is_file() and f.name.startswith("playit"):
                if f.name == self.version_marker_path.name:
                    continue
                if self.binary_path.exists() and f.samefile(self.binary_path):
                    continue
                try:
                    f.unlink()
                    logger.info("[Playit] Removed stale binary: %s", f.name)
                except OSError:
                    pass

    def ensure_binary(self) -> bool:
        if not BIN_DIR.exists():
            BIN_DIR.mkdir(parents=True, exist_ok=True)

        self._clean_stale_binaries()

        if self.binary_path.exists():
            installed = ""
            if self.version_marker_path.exists():
                try:
                    installed = self.version_marker_path.read_text(encoding="utf-8").strip()
                except OSError:
                    installed = ""
            if installed == PLAYIT_VERSION:
                return True
            self.console_callback(f"[Playit] Found old version. Updating to {PLAYIT_VERSION}...")
            try:
                os.remove(self.binary_path)
            except OSError:
                self.stop(force=True)
                time.sleep(0.5)
                try:
                    os.remove(self.binary_path)
                except Exception as e2:
                    self.console_callback(f"[Playit] Could not remove old binary: {e2}")
                    return False

        url = PLAYIT_URL_WINDOWS if platform.system() == "Windows" else PLAYIT_URL_LINUX
        self.console_callback(f"[Playit] Downloading agent v{PLAYIT_VERSION} from {url}...")

        # Download to a temp name (must NOT start with "playit" or
        # _clean_stale_binaries will touch it), verify size + smoke-test
        # the binary, then atomically replace. Prevents a truncated or
        # arch-mismatched download from being installed and triggering
        # an infinite version-check-fail -> redownload loop (WinError 216).
        tmp_path = BIN_DIR / "agent_download.tmp"
        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            with open(tmp_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            size = tmp_path.stat().st_size
            if size < 1_000_000:
                self.console_callback(f"[Playit] Download truncated ({size} bytes). Aborting install.")
                return False

            if platform.system() != "Windows":
                tmp_path.chmod(0o755)

            # playitd has no "version" subcommand; "--help" exits 0 and proves
            # the binary executes on this machine.
            try:
                result = subprocess.run(
                    [str(tmp_path), "--help"],
                    capture_output=True, text=True, check=False, timeout=15,
                    **subprocess_flags(),
                )
            except OSError as e:
                if getattr(e, "winerror", None) == 216:
                    self.console_callback(
                        "[Playit] Downloaded agent is not compatible with this Windows "
                        "(CPU architecture mismatch?). Not installing it."
                    )
                else:
                    self.console_callback(f"[Playit] Downloaded agent failed to run ({e}). Not installing it.")
                return False

            if result.returncode != 0 or not (result.stdout + result.stderr).strip():
                self.console_callback("[Playit] Downloaded agent failed smoke test. Not installing it.")
                return False

            os.replace(tmp_path, self.binary_path)
            self.version_marker_path.write_text(PLAYIT_VERSION, encoding="utf-8")
            self.console_callback("[Playit] Download complete.")
            return True
        except Exception as e:
            self.console_callback(f"[Playit] Download failed: {e}")
            return False
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def get_or_create_tunnel(self, port: int) -> Optional[str]:
        if not self.api_client.load_secret_key():
            self.console_callback("[Playit] Agent not linked yet.")
            return None

        try:
            tunnels = self.api_client.list_tunnels()
            for t in tunnels:
                origin_port = t.get("origin", {}).get("data", {}).get("local_port")
                if origin_port == port:
                    address = self.api_client.get_tunnel_address(t)
                    if address:
                        self._api_dns = address
                        return address

            # Free tier allows only 4 port allocations account-wide. Tunnels
            # left behind by previous agents (failed re-links) hold ports and
            # make new tunnels stay pending forever — purge ours first.
            try:
                self._cleanup_stale_tunnels()
            except PlayitApiException as e:
                logger.warning("[Playit] Stale tunnel cleanup failed: %s", e)

            self.console_callback(f"[Playit] No tunnel for port {port}. Creating via API...")
            tunnel = self.api_client.create_tunnel(port)
            if tunnel:
                address = self.api_client.get_tunnel_address(tunnel)
                if address:
                    self._api_dns = address
                    return address
                self.console_callback("[Playit] Tunnel created but no public address was allocated after 15s.")
                self.console_callback("[Playit] Port quota may be exhausted (free tier: 4 ports). Delete unused tunnels/agents at https://playit.gg/dashboard")
                if self.notification_callback:
                    self.notification_callback("Tunnel pending: no ports available. Check playit.gg dashboard.", "warning")
            return None

        except PlayitApiException as e:
            if "NotAllowedWithReadOnly" in str(e):
                self.console_callback("[Playit] ERROR: Account is in Guest mode (Read-Only).")
                self.console_callback("[Playit] Please use 'Get Code' + 'Link' with a Setup Code to enable tunnel creation.")
                if self.notification_callback:
                    self.notification_callback("Account Read-Only. Use Setup Code to link.", "error")
            else:
                self.console_callback(f"[Playit] API Error: {e}")
            return None

    def _cleanup_stale_tunnels(self) -> None:
        """Delete minecraft-java_* tunnels owned by other agents on the account.
        Only touches tunnels matching our own generated name pattern — user-made
        tunnels and other machines' tunnels are left alone."""
        agent_id = self.api_client.get_agent_id()
        if not agent_id:
            return
        for t in self.api_client.list_account_tunnels():
            name = t.get("name") or ""
            owner = t.get("origin", {}).get("data", {}).get("agent_id")
            tid = t.get("id")
            if not tid or owner == agent_id:
                continue
            if re.fullmatch(r"minecraft-java_[a-z0-9]{4}", name):
                try:
                    if self.api_client.delete_tunnel(tid):
                        self.console_callback(f"[Playit] Freed port: deleted stale tunnel {name} from a previous agent.")
                except PlayitApiException as e:
                    logger.warning("[Playit] Could not delete stale tunnel %s: %s", tid, e)

    def _create_tunnel_from_stdout(self, port: int) -> None:
        # Runs off the stdout reader thread: agent reported 0 tunnels but its
        # control connection stays alive, so the heartbeat's dead-process branch
        # never fires — create the tunnel via API immediately instead.
        try:
            if self.api_client.initialize():
                address = self.get_or_create_tunnel(port)
                if address:
                    with self._lock:
                        self._api_dns = address
                        self.current_address = address
                    self.console_callback(f"[Playit] Tunnel created: {address}")
                    self.status_callback("Online", address)
            else:
                self.console_callback(
                    "[Playit] No tunnels configured. Create one at https://playit.gg/dashboard"
                )
        except Exception as e:
            logger.warning("[Playit] Tunnel create failed: %s", e)
        finally:
            with self._lock:
                self._tunnel_create_inflight = False

    def start(self, port: int = 25565) -> None:
        with self._lock:
            if self.running:
                self.console_callback("[Playit] Agent already running.")
                if self._api_dns:
                    self.current_address = self._api_dns
                    self.status_callback("Online", self._api_dns)
                return

        try:
            self._start_internal(port)
        except Exception as e:
            logger.error("[PlayitManager] Fatal error in start thread: %s", e)
            self.console_callback(f"[Playit] Internal start failure: {e}")
            self.status_callback("Error", None)

    def _start_internal(self, port: int) -> None:
        with self._lock:
            self._api_dns = None
            self.current_address = None
            self._current_port = port
            self._auth_failed = False
            self._tunnel_create_inflight = False

        self.status_callback("Starting...", None)

        if not self.ensure_binary():
            self.console_callback("[Playit] Binary check failed.")
            return

        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)

        self.is_linked = os.path.exists(self.toml_path)
        if not self.is_linked:
            self.console_callback("[Playit] No playit.toml found. Link account first.")
            return

        # Validate the stored secret before launching — a dead key otherwise
        # sends the agent into an invalid-secret loop the user can't escape.
        self.api_client.load_secret_key()
        if self.api_client.secret_rejected():
            self._handle_auth_failure("Stored agent secret rejected by API (401)")
            return

        self.api_client.is_read_only = False
        self._kill_stale_agents()
        self.console_callback("[Playit] Launching tunnel agent...")

        try:
            env = os.environ.copy()
            env["RUST_LOG"] = "debug"

            self.api_client.load_secret_key()
            env["PLAYIT_SECRET_KEY"] = self.api_client._secret_key or ""

            # playitd (v1.0+): no --stdout flag, logs go to stderr (merged into
            # the stdout pipe below). Custom IPC socket avoids clashing with an
            # officially installed playitd service. Must be the namespaced
            # "@name" form — the daemon rejects raw \\.\pipe\ paths at bind.
            cmd = [
                str(self.binary_path),
                "--secret-path", str(self.toml_path),
                "--socket-path", "@zbb-playitd",
            ]

            kwargs = subprocess_flags()
            if platform.system() != "Windows":
                kwargs["preexec_fn"] = os.setsid

            self.process = subprocess.Popen(
                cmd,
                cwd=os.path.abspath(CONFIG_DIR),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                **kwargs,
            )
            self._assign_to_job(self.process.pid)
            self.running = True
            if not self.current_address:
                self.status_callback("Starting...", None)

            threading.Thread(target=self._read_output, daemon=True).start()
            threading.Thread(target=self._dns_polling_loop, daemon=True).start()
            threading.Thread(target=self._heartbeat_loop, daemon=True).start()

        except OSError as e:
            self.console_callback(f"[Playit] Failed to start: {e}")
            self.running = False
            self.status_callback("Error", None)

    def _kill_stale_agents(self) -> None:
        """Kill orphaned playit agents left over from a previous app run.

        A hard kill of the app (Ctrl+C on the console, taskkill, crash)
        skips atexit, leaving playitd alive holding a control session.
        That stale session then fights the new agent over tunnel
        assignment (tunnel_count flapping 1->0->1 every ~6s).
        Only processes running OUR binary path are touched.
        """
        try:
            import psutil
        except ImportError:
            return
        target = os.path.normcase(str(self.binary_path))
        for proc in psutil.process_iter(["pid", "exe"]):
            try:
                exe = proc.info.get("exe")
                if exe and os.path.normcase(exe) == target:
                    proc.kill()
                    logger.info("[Playit] Killed stale agent process pid=%d", proc.info["pid"])
                    self.console_callback("[Playit] Killed stale agent from a previous session.")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def _assign_to_job(self, pid: int) -> None:
        """Bind the agent to a Windows Job Object with KILL_ON_JOB_CLOSE.

        The OS then reaps playitd even when this process dies without
        running atexit (console closed, taskkill, interpreter crash).
        No-op on non-Windows (setsid + stop() covers POSIX).
        """
        if platform.system() != "Windows":
            return
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32
            job = kernel32.CreateJobObjectW(None, None)
            if not job:
                return

            class _BasicLimits(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class _IoCounters(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_uint64),
                    ("WriteOperationCount", ctypes.c_uint64),
                    ("OtherOperationCount", ctypes.c_uint64),
                    ("ReadTransferCount", ctypes.c_uint64),
                    ("WriteTransferCount", ctypes.c_uint64),
                    ("OtherTransferCount", ctypes.c_uint64),
                ]

            class _ExtendedLimits(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", _BasicLimits),
                    ("IoInfo", _IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
            JobObjectExtendedLimitInformation = 9
            info = _ExtendedLimits()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            kernel32.SetInformationJobObject(
                job, JobObjectExtendedLimitInformation,
                ctypes.byref(info), ctypes.sizeof(info),
            )

            PROCESS_SET_QUOTA = 0x0100
            PROCESS_TERMINATE = 0x0001
            handle = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
            if handle:
                if not kernel32.AssignProcessToJobObject(job, handle):
                    logger.debug("[Playit] AssignProcessToJobObject failed: %d", kernel32.GetLastError())
                kernel32.CloseHandle(handle)
            # Keep the job handle alive for the app's lifetime — closing it
            # (including at process death) is what kills the agent.
            self._job_handle = job
        except Exception as e:
            logger.debug("[Playit] Job object assignment failed: %s", e)

    def stop(self, force: bool = False) -> None:
        with self._lock:
            proc = self.process
            self.process = None
            if proc:
                self.console_callback("[Playit] Stopping agent...")
                pid = proc.pid
                killed = False
                try:
                    import psutil
                    parent = psutil.Process(pid)
                    for child in parent.children(recursive=True):
                        try:
                            child.kill()
                        except Exception:
                            pass
                    parent.kill()
                    killed = True
                except Exception as e:
                    logger.debug("psutil stop error: %s", e)

                if not killed:
                    if platform.system() == "Windows":
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(pid)],
                            capture_output=True, check=False,
                            **subprocess_flags(),
                        )
                    else:
                        try:
                            proc.terminate()
                        except Exception as te:
                            logger.debug("subprocess terminate error: %s", te)

                # Block until OS confirms the process is gone (max 3s).
                # This prevents sys.exit() from racing ahead of kill completion.
                try:
                    proc.wait(timeout=3)
                except Exception:
                    pass  # Already dead or timed out — either is acceptable.

            if force and platform.system() == "Windows":
                # Nuclear option: kill any stray playit process by image name.
                # Uses CREATE_NO_WINDOW — no flash, silent noop if nothing running.
                for proc_name in ["playit.exe", "playit-cli.exe"]:
                    subprocess.run(
                        ["taskkill", "/F", "/IM", proc_name],
                        capture_output=True, check=False,
                        **subprocess_flags(),
                    )

            self.running = False
            self.current_address = None
            self._api_dns = None
            self.status_callback("Offline", None)

    def reset(self, mode: str = "full") -> None:
        try:
            if mode != "full" and self._auth_failed:
                # Soft reset keeps playit.toml, so a rejected secret would just
                # relaunch into the same auth loop — force a full re-link instead.
                self.console_callback("[Playit] Stored secret is invalid. Escalating to full reset to force re-link.")
                mode = "full"
            if mode == "full":
                self.console_callback("[Playit] Starting full reset...")
            else:
                self.console_callback("[Playit] Starting tunnel-only reset...")

            # --- CRITICAL DNS: load secret key from toml for remote cleanup ---
            self.api_client.load_secret_key()

            # 1. Delete remote tunnels (both modes)
            self.console_callback("[Playit] Cleaning up remote tunnels...")
            try:
                tunnels = self.api_client.list_tunnels()
                for t in tunnels:
                    tid = t.get("id")
                    if tid:
                        try:
                            if self.api_client.delete_tunnel(tid):
                                self.console_callback(f"[Playit] Deleted tunnel: {tid}")
                        except Exception as e:
                            self.console_callback(f"[Playit] Tunnel delete failed: {e}")
            except Exception as e:
                self.console_callback(f"[Playit] Tunnel list failed: {e}")

            # 2. Stop local process (both modes)
            self.stop()

            if mode == "full":
                # Full reset: also delete agent, config, credentials
                self.console_callback("[Playit] Cleaning up remote agent...")
                api_deleted = False
                try:
                    api_deleted = self.api_client.delete_agent()
                    if api_deleted:
                        self.console_callback("[Playit] Remote agent deleted via API.")
                except Exception as e:
                    self.console_callback(f"[Playit] API agent deletion failed (agent may remain in dashboard): {e}")

                if not api_deleted:
                    self.console_callback("[Playit] Agent could not be deleted automatically. If it remains, delete manually at:")
                    self.console_callback("[Playit] https://playit.gg/dashboard/agents")

                if os.path.exists(self.toml_path):
                    os.remove(self.toml_path)
                    self.console_callback("[Playit] Local config playit.toml removed.")

                self.is_linked = False
                self.api_client.is_read_only = False
                self.api_client._secret_key = None
                self.api_client._agent_id = None
                self.api_client.consecutive_auth_failures = 0
                self._auth_failed = False
                self.current_address = None
                self._api_dns = None
                self.console_callback("[Playit] Account unlinked and reset complete.")
                if self.notification_callback:
                    self.notification_callback("Playit account unlinked and reset.", "success")
            else:
                # Soft reset: keep agent linked, user can create a new tunnel with ▶
                self.current_address = None
                self._api_dns = None
                self.console_callback("[Playit] Tunnels cleared. Agent stays linked. Click ▶ to create a new tunnel.")
                if self.notification_callback:
                    self.notification_callback("Tunnels cleared. Click ▶ to create a new tunnel.", "success")
        except Exception as e:
            self.console_callback(f"[Playit] Reset failed: {e}")

    def link_manually(self, setup_code: str) -> bool:
        if not setup_code or len(setup_code.strip()) < 8:
            self.console_callback("[Playit] Invalid setup code. Must be at least 8 characters.")
            if self.notification_callback:
                self.notification_callback("Invalid setup code.", "error")
            return False

        # Download binary proactively before linking
        self.ensure_binary()

        clean_code = setup_code.strip()
        try:
            self.console_callback(f"[Playit] Exchanging setup code with secure bridge...")
            if self.api_client.link_account(clean_code):
                self.console_callback("[Playit] Account linked successfully! Starting agent...")
                self.is_linked = True
                self._linked_at = time.time()
                self.api_client.is_read_only = False

                if self.running:
                    self.stop(force=True)

                self.start(getattr(self, '_current_port', 25565))
                return True
        except Exception as e:
            self.console_callback(f"[Playit] Link failed: {e}")
            if self.notification_callback:
                self.notification_callback(f"Link failed: {e}", "error")
        return False

    def _handle_auth_failure(self, reason: str) -> None:
        """Mark the agent secret as dead and tell the user to re-link.
        Idempotent — only the first caller emits the error output."""
        with self._lock:
            if self._auth_failed:
                return
            self._auth_failed = True
        self.status_callback("Error", None)
        self.console_callback(f"[Playit] ERROR: {reason}. Use 'Reset Tunnel' to re-link.")
        # A secret revoked minutes after a successful link means playit killed
        # the agent server-side — almost always an account over its agent/port
        # limit, and re-linking will just create more dead agents.
        if time.time() - getattr(self, "_linked_at", 0) < 300:
            self.console_callback("[Playit] Secret was revoked right after linking. Your account is likely over its agent/port limit.")
            self.console_callback("[Playit] Delete old agents and tunnels at https://playit.gg/dashboard/agents BEFORE re-linking.")
        if self.notification_callback:
            self.notification_callback("Playit secret invalid. Use 'Reset Tunnel' to re-link.", "error")

    def _fix_permissions(self) -> None:
        if platform.system() != "Windows" and os.path.exists(self.toml_path):
            try:
                mode = os.stat(self.toml_path).st_mode
                if mode & 0o077:
                    os.chmod(self.toml_path, 0o600)
                    logger.info("Fixed playit.toml permissions to 600")
            except Exception as e:
                logger.warning("Could not fix playit.toml permissions: %s", e)

    # --- CRITICAL DNS: polls API indefinitely until DNS resolves or manager stops ---
    # DO NOT MODIFY without understanding the full DNS recovery chain:
    # 1. get_or_create_tunnel() (15s window in create_tunnel)
    # 2. _dns_polling_loop() (infinite API poll - THIS METHOD)
    # 3. _parse_line() (stdout regex from agent)
    def _dns_polling_loop(self) -> None:
        polls = 0
        while True:
            with self._lock:
                if not self.running:
                    return
            time.sleep(5)
            polls += 1
            with self._lock:
                if not self.running:
                    return
                if self._api_dns or self._stdout_dns:
                    return
            # playitd (v1.0+) never prints "agent has 0 tunnels" like the old
            # CLI did, so the stdout create-trigger no longer fires. If the
            # agent has been up for a few polls with no tunnel, ensure one
            # exists via the API (inflight guard prevents duplicate creates).
            if polls == 3:
                with self._lock:
                    already_running = self._tunnel_create_inflight or self._api_dns
                    if not already_running:
                        self._tunnel_create_inflight = True
                if not already_running:
                    self.console_callback("[Playit] No public address yet. Ensuring tunnel exists via API...")
                    threading.Thread(
                        target=self._create_tunnel_from_stdout,
                        args=(self._current_port,), daemon=True,
                    ).start()
            try:
                addresses = self.api_client.get_tunnels()
                if addresses:
                    address = addresses[0]
                    with self._lock:
                        if address == self.current_address:
                            continue
                        self.current_address = address
                        self._api_dns = address
                    self.status_callback("Online", address)
                    self.console_callback(f"[Playit] Public address: {address}")
                    if self.notification_callback:
                        self.notification_callback(f"Tunnel online: {address}", "success")
                    if self.on_ready_callback:
                        self.on_ready_callback()
                    return
            except Exception as e:
                logger.warning("[Playit] DNS polling error: %s", e)
            # get_tunnels() swallows API exceptions, so a dead secret surfaces
            # here only as the client's consecutive 401 count — stop polling
            # instead of hammering the API every 5s forever.
            if self.api_client.consecutive_auth_failures >= 3:
                self._handle_auth_failure("API rejected the agent secret repeatedly")
                return

    def _heartbeat_loop(self) -> None:
        max_attempts = 10
        attempt_count = 0
        backoff = 1
        
        while True:
            with self._lock:
                if not self.running:
                    break
            time.sleep(15)
            with self._lock:
                if not self.running:
                    break
                
                is_dead = (self.process is None or self.process.poll() is not None)
            
            if is_dead:
                # Auth failures are not recoverable by restart — user must re-link
                if self._auth_failed:
                    logger.warning("[Playit] Heartbeat: agent exited due to auth failure — not restarting.")
                    break

                attempt_count += 1
                logger.warning("[Playit] Heartbeat #%d: process not running.", attempt_count)
                if attempt_count >= max_attempts:
                    self.console_callback("[Playit] CRITICAL: Max restart attempts reached. Agent halted.")
                    if self.notification_callback:
                        self.notification_callback("Playit agent failed to start after multiple attempts.", "error")
                    break
                else:
                    self.console_callback(f"[Playit] Agent dead. Restarting in {backoff}s (Attempt {attempt_count}/{max_attempts})...")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 300)
                    port = getattr(self, '_current_port', 25565)
                    threading.Thread(target=self.start, args=(port,), daemon=True).start()
            else:
                attempt_count = 0
                backoff = 1

    SPAM_LOGS = [
        "tunnel running", "udp channel requires auth", "udp session details received",
        "send KeepAlive", "agent registered details", "authenticate control last_pong",
        "session expired reason=SessionNotSetup",
        "reconnecting reason=SessionNotSetup",
        "playit tunnel state updated",
        "failed to send initial ping error=Os { code: 10051",
        "failed to send initial ping error=Os { code: 101", "failed to ping tunnel server",
        "failed to parse json", "ReqProtoRegister",
        "NetworkUnreachable"
    ]

    # --- CRITICAL DNS: regex-based domain extraction from agent stdout ---
    # DO NOT MODIFY. This is the 3rd and final DNS recovery mechanism.
    # Extracts .ply.gg / .playit.gg / .joinmc.link domains from agent log lines.
    def _parse_line(self, line: str) -> None:
        if not line:
            return
        if self._api_dns or self._stdout_dns:
            return
        dns_patterns = [
            r"([a-z0-9][a-z0-9-]*\.(?:gl\.)?(?:ply|playit)\.gg(?::\d+)?)",
            r"([a-z0-9][a-z0-9-]*\.(?:gl\.)?joinmc\.link(?::\d+)?)",
        ]
        for pattern in dns_patterns:
            dns_match = re.search(pattern, line)
            if dns_match:
                address = dns_match.group(1).rstrip('.')
                with self._lock:
                    if address == self.current_address:
                        return
                    self._stdout_dns = address
                    self.current_address = address
                self.status_callback("Online", address)
                self.console_callback(f"[Playit] Public address: {address}")
                if self.notification_callback:
                    self.notification_callback(f"Tunnel online: {address}", "success")
                if self.on_ready_callback:
                    self.on_ready_callback()
                return

    def _read_output(self) -> None:
        try:
            while self.running and self.process:
                try:
                    raw = self.process.stdout.readline()
                except Exception as e:
                    logger.warning("[Playit] readline error: %s", e)
                    break
                if not raw:
                    break
                try:
                    line = raw.decode('utf-8', errors='replace').strip()
                except Exception as e:
                    logger.warning("[Playit] decode error: %s", e)
                    continue
                if line:
                    clean_line = ANSI_ESCAPE_RE.sub('', line)
                    is_spam = any(s in clean_line for s in self.SPAM_LOGS)
                    if not is_spam:
                        self.console_callback(f"[Playit] {clean_line}")
                    if ("AgentDisabledOverLimit" in clean_line or "Account limit reached" in clean_line
                            or "account agent limit" in clean_line):
                        self.status_callback("Error", None)
                        self.console_callback("[Playit] ERROR: Account limit reached!")
                        self.console_callback("[Playit] You have too many agents. Delete unused agents at https://playit.gg/dashboard/agents")
                        self._auth_failed = True
                    elif ("Invalid secret" in clean_line or "invalid secret" in clean_line
                          or "InvalidAgentKey" in clean_line
                          or "secret is no longer valid" in clean_line):
                        # Corrupted/expired secret key — auth error, user must re-link.
                        # InvalidAgentKey is a 401, NOT a missing-tunnel condition.
                        self._handle_auth_failure("Agent secret invalid")
                    elif "agent has 0 tunnels" in clean_line:
                        # Agent has no tunnels configured. The agent repeats this line
                        # on reconnect attempts — inflight flag ensures only one
                        # create runs at a time (get_or_create_tunnel is list-then-create,
                        # so two concurrent calls could create duplicate tunnels).
                        with self._lock:
                            already_running = self._tunnel_create_inflight or self._api_dns
                            if not already_running:
                                self._tunnel_create_inflight = True
                        if not already_running:
                            self.console_callback("[Playit] No tunnel found. Creating tunnel via API...")
                            threading.Thread(
                                target=self._create_tunnel_from_stdout,
                                args=(self._current_port,), daemon=True,
                            ).start()
                    elif "Got Error" in clean_line:
                        # Generic agent-side failure (e.g. tunnel registration never
                        # completed because no port could be allocated). Without this
                        # the UI sits on "Starting..." forever.
                        with self._lock:
                            has_dns = self._api_dns or self._stdout_dns
                        if not has_dns:
                            self.status_callback("Error", None)
                            self.console_callback("[Playit] Agent reported an error before getting an address.")
                            self.console_callback("[Playit] Check tunnels and port quota at https://playit.gg/dashboard")
                    # --- CRITICAL DNS: must call _parse_line on every line ---
                    self._parse_line(clean_line)
        except Exception as e:
            self.console_callback(f"[Playit] Read error: {e}")
        finally:
            with self._lock:
                self.running = False
                self.process = None
                addr = self._api_dns or self._stdout_dns
                self.current_address = addr if addr else None
            self.status_callback("Offline", None)


