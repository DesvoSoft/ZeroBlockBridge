"""Handles for long operations: progress, cancellation and completion.

A ``Task`` wraps one background job. The job receives the task and calls
``task.report(...)`` for progress and checks ``task.cancel_event`` (the same
``threading.Event`` the provisioning code already polls between steps and
download chunks). Progress and completion callbacks go through the task's
dispatcher, so a UI receives them on its own thread.
"""

import concurrent.futures
import logging
import threading
from typing import Any, Callable, Optional

from app.api.events import Dispatcher, direct

logger = logging.getLogger(__name__)


class Task:
    def __init__(self, name: str = "", dispatcher: Dispatcher = direct, cancellable: bool = True):
        self.name = name
        self.cancellable = cancellable
        self.cancel_event = threading.Event()
        self._dispatcher = dispatcher
        self._future: concurrent.futures.Future = concurrent.futures.Future()
        self._progress: list[Callable] = []
        self._done: list[Callable] = []
        self._lock = threading.Lock()

    # -- caller side ---------------------------------------------------
    def on_progress(self, callback: Callable[..., None]) -> "Task":
        with self._lock:
            self._progress.append(callback)
        return self

    def on_done(self, callback: Callable[["Task"], None]) -> "Task":
        """``callback(task)`` once finished (at once if it already is)."""
        with self._lock:
            finished = self._future.done()
            if not finished:
                self._done.append(callback)
        if finished:
            self._dispatcher(lambda: callback(self))
        return self

    def cancel(self) -> bool:
        """Ask the job to stop. False when this kind of task can't be cancelled."""
        if not self.cancellable:
            return False
        self.cancel_event.set()
        return True

    @property
    def cancel_requested(self) -> bool:
        return self.cancel_event.is_set()

    def done(self) -> bool:
        return self._future.done()

    def result(self, timeout: Optional[float] = None) -> Any:
        return self._future.result(timeout)

    def exception(self, timeout: Optional[float] = None) -> Optional[BaseException]:
        return self._future.exception(timeout)

    # -- job side --------------------------------------------------------
    def report(self, *args) -> None:
        with self._lock:
            listeners = list(self._progress)
        for callback in listeners:
            self._dispatcher(lambda cb=callback: cb(*args))

    def _run(self, job: Callable[["Task"], Any]) -> None:
        try:
            self._future.set_result(job(self))
        except Exception as exc:
            logger.exception("Task %s failed", self.name or job)
            self._future.set_exception(exc)
        with self._lock:
            callbacks, self._done = self._done, []
        for callback in callbacks:
            self._dispatcher(lambda cb=callback: cb(self))


class TaskRunner:
    """Starts tasks on an executor and remembers the unfinished ones, so the
    app can cancel them all on exit."""

    def __init__(self, executor: concurrent.futures.Executor, dispatcher_source: Callable[[], Dispatcher]):
        self._executor = executor
        self._dispatcher_source = dispatcher_source
        self._active: set[Task] = set()
        self._lock = threading.Lock()

    def start(self, name: str, job: Callable[[Task], Any], cancellable: bool = True) -> Task:
        task = Task(name, self._dispatcher_source(), cancellable)
        with self._lock:
            self._active.add(task)

        def run():
            try:
                task._run(job)
            finally:
                with self._lock:
                    self._active.discard(task)

        self._executor.submit(run)
        return task

    def active(self, name: Optional[str] = None) -> list[Task]:
        with self._lock:
            return [t for t in self._active if name is None or t.name == name]

    def cancel_all(self) -> None:
        for task in self.active():
            task.cancel()
