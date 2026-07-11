"""Process lifecycle helper — cross-platform orphan prevention.

Windows: Job Object with KILL_ON_JOB_CLOSE reaps children when the parent
dies (including hard kills that skip atexit).  Nested children (e.g.
Fabric's inner java) inherit the job automatically.

Linux: prctl(PR_SET_PDEATHSIG, SIGKILL) tells the kernel to send SIGKILL
to the child when its parent exits.  After setsid() the child is
reparented to init, so we also check the parent PID to detect a race
where the parent dies between fork and setsid.
"""
import logging
import os
import platform
import signal

logger = logging.getLogger(__name__)

# Windows: job handles must stay referenced for the app's lifetime — closing
# the handle (which the OS does at process death) is what kills the job.
_handles = []


def assign_to_job(pid: int) -> None:
    """Bind *pid* to the current process so it is reaped on exit.

    On Windows this uses Job Objects (KILL_ON_JOB_CLOSE).
    On Linux this is a no-op — reaping is set up via ``preexec_fn`` at
    spawn time (see ``linux_preexec()``).
    """
    if platform.system() != "Windows":
        return
    if not isinstance(pid, int):
        logger.debug("assign_to_job called with non-int pid %r, skipping", pid)
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
                logger.debug("AssignProcessToJobObject failed for pid %d: %d", pid, kernel32.GetLastError())
            kernel32.CloseHandle(handle)
        _handles.append(job)
    except Exception as e:
        logger.debug("Job object assignment failed for pid %d: %s", pid, e)


# ---------------------------------------------------------------------------
# Linux preexec helper
# ---------------------------------------------------------------------------
# libc is resolved at import time (in the parent): preexec_fn runs in the
# forked child before exec, where imports and logging can deadlock on locks
# held by other threads at fork time — the preexec body must stay minimal.
_PR_SET_PDEATHSIG = 1
_libc = None
if platform.system() != "Windows":
    try:
        import ctypes
        import ctypes.util

        _libc_name = ctypes.util.find_library("c")
        if _libc_name:
            _libc = ctypes.CDLL(_libc_name, use_errno=True)
    except OSError as e:
        logger.debug("libc load failed, PDEATHSIG unavailable: %s", e)


def linux_preexec() -> None:
    """``preexec_fn`` for subprocess.Popen on Linux.

    Sets PR_SET_PDEATHSIG so the child is killed when the parent exits,
    then checks for reparenting: if the parent died between fork and the
    prctl call, the child was reparented to init (ppid 1) and PDEATHSIG
    will never fire — exit immediately instead of surviving as an orphan.
    """
    if _libc is not None:
        _libc.prctl(_PR_SET_PDEATHSIG, signal.SIGKILL)
    if os.getppid() == 1:
        os._exit(1)
