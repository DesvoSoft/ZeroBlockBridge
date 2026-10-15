"""Event delivery through a caller-supplied dispatcher, and task handles
(progress, completion, cancellation) of the API seam."""

import concurrent.futures
import threading

import pytest

from app.api.events import EventHub, direct
from app.api.tasks import Task, TaskRunner
from app.core.server_events import EventBus, ServerEvent


class QueueDispatcher:
    """Stands in for a UI main loop: runs nothing until pumped."""

    def __init__(self):
        self.queue = []

    def __call__(self, fn):
        self.queue.append(fn)

    def pump(self):
        while self.queue:
            self.queue.pop(0)()


class TestEventHub:
    def test_handler_runs_only_through_the_dispatcher(self):
        bus, loop, got = EventBus(), QueueDispatcher(), []
        EventHub(bus, loop).subscribe(ServerEvent.CONSOLE_LINE, got.append)
        bus.emit(ServerEvent.CONSOLE_LINE, "a")
        bus.emit(ServerEvent.CONSOLE_LINE, "b")
        assert got == []
        loop.pump()
        assert got == ["a", "b"]

    def test_emitting_thread_never_runs_the_handler(self):
        bus, loop, threads = EventBus(), QueueDispatcher(), []
        EventHub(bus, loop).subscribe(ServerEvent.READY, lambda _d: threads.append(threading.current_thread()))
        worker = threading.Thread(target=bus.emit, args=(ServerEvent.READY, None))
        worker.start()
        worker.join()
        loop.pump()
        assert threads == [threading.current_thread()]

    def test_cancel_drops_already_queued_calls(self):
        bus, loop, got = EventBus(), QueueDispatcher(), []
        sub = EventHub(bus, loop).subscribe(ServerEvent.CONSOLE_LINE, got.append)
        bus.emit(ServerEvent.CONSOLE_LINE, "queued")
        sub.cancel()
        bus.emit(ServerEvent.CONSOLE_LINE, "after")
        loop.pump()
        assert got == []
        assert not sub.active
        sub.cancel()  # idempotent

    def test_per_subscription_dispatcher_overrides_the_default(self):
        bus, loop, got = EventBus(), QueueDispatcher(), []
        hub = EventHub(bus, loop)
        hub.subscribe(ServerEvent.STOPPED, got.append, dispatcher=direct)
        bus.emit(ServerEvent.STOPPED, 1)
        assert got == [1] and loop.queue == []

    def test_set_dispatcher_applies_to_later_subscriptions(self):
        bus, loop, got = EventBus(), QueueDispatcher(), []
        hub = EventHub(bus)
        assert hub.dispatcher is direct
        hub.set_dispatcher(loop)
        hub.subscribe(ServerEvent.PLAYER_COUNT, got.append)
        bus.emit(ServerEvent.PLAYER_COUNT, 3)
        assert got == []
        loop.pump()
        assert got == [3]

    def test_close_cancels_every_subscription(self):
        bus, got = EventBus(), []
        hub = EventHub(bus)
        hub.subscribe(ServerEvent.READY, got.append)
        hub.subscribe(ServerEvent.STOPPED, got.append)
        hub.close()
        bus.emit(ServerEvent.READY, 1)
        bus.emit(ServerEvent.STOPPED, 2)
        assert got == []

    def test_handler_error_is_contained_by_the_bus(self):
        bus, got = EventBus(), []
        hub = EventHub(bus)
        hub.subscribe(ServerEvent.READY, lambda _d: 1 / 0)
        hub.subscribe(ServerEvent.READY, got.append)
        bus.emit(ServerEvent.READY, "ok")
        assert got == ["ok"]


def _runner(loop=None):
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    return TaskRunner(executor, lambda: loop or direct), executor


class TestTask:
    def test_progress_and_done_go_through_the_dispatcher(self):
        loop = QueueDispatcher()
        runner, executor = _runner(loop)
        progress, done = [], []

        def job(task):
            task.report(0.5, "half")
            return "result"

        task = runner.start("job", job).on_progress(lambda *a: progress.append(a)).on_done(done.append)
        executor.shutdown(wait=True)
        assert progress == [] and done == []
        loop.pump()
        assert done == [task]
        assert task.result(timeout=1) == "result"

    def test_progress_listener_added_before_report(self):
        task, got = Task(), []
        task.on_progress(lambda *a: got.append(a))
        task.report(0.25, "x")
        assert got == [(0.25, "x")]

    def test_on_done_after_completion_fires_at_once(self):
        task, got = Task(), []
        task._run(lambda t: 42)
        task.on_done(got.append)
        assert got == [task] and task.done()

    def test_cancel_sets_the_event_the_job_polls(self):
        runner, executor = _runner()
        started, finished = threading.Event(), []

        def job(task):
            started.set()
            task.cancel_event.wait(timeout=5)
            finished.append(task.cancel_requested)
            return "stopped"

        task = runner.start("create_server", job)
        started.wait(timeout=5)
        assert runner.active("create_server") == [task]
        assert task.cancel() is True
        assert task.result(timeout=5) == "stopped"
        executor.shutdown(wait=True)
        assert finished == [True]
        assert runner.active() == []

    def test_cancel_all_reaches_every_running_task(self):
        runner, executor = _runner()
        gate = threading.Barrier(3)

        def job(task):
            gate.wait(timeout=5)
            return task.cancel_event.wait(timeout=5)

        tasks = [runner.start("a", job), runner.start("b", job)]
        gate.wait(timeout=5)
        runner.cancel_all()
        assert [t.result(timeout=5) for t in tasks] == [True, True]
        executor.shutdown(wait=True)

    def test_non_cancellable_task_refuses(self):
        task = Task(cancellable=False)
        assert task.cancel() is False
        assert not task.cancel_requested

    def test_job_exception_is_kept_and_done_still_fires(self):
        done = []
        task = Task().on_done(done.append)
        task._run(lambda t: (_ for _ in ()).throw(RuntimeError("boom")))
        assert done == [task]
        assert isinstance(task.exception(timeout=1), RuntimeError)
        with pytest.raises(RuntimeError):
            task.result(timeout=1)


class TestTaskEndsAreAlwaysReported:
    """Regressions: a task must finish (and say so) whatever happens to its
    job, its executor or the UI it reports to — or a progress dialog stays
    open and the task counts as running forever."""

    def test_base_exception_still_completes_the_task(self):
        done = []
        task = Task().on_done(done.append)
        with pytest.raises(KeyboardInterrupt):
            task._run(lambda t: (_ for _ in ()).throw(KeyboardInterrupt()))
        assert done == [task] and task.done()

    def test_submit_to_a_shut_down_executor_fails_the_task(self):
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        executor.shutdown()
        runner = TaskRunner(executor, lambda: direct)
        done = []
        task = runner.start("x", lambda t: 1).on_done(done.append)
        assert done == [task]
        assert isinstance(task.exception(timeout=1), RuntimeError)
        assert runner.active() == []

    def test_job_dropped_from_the_queue_fails_the_task(self):
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        runner = TaskRunner(executor, lambda: direct)
        release = threading.Event()
        first = runner.start("busy", lambda t: release.wait(timeout=5))
        queued = runner.start("queued", lambda t: "never")
        executor.shutdown(wait=False, cancel_futures=True)
        release.set()
        assert first.result(timeout=5) is True
        with pytest.raises(concurrent.futures.CancelledError):
            queued.result(timeout=5)
        assert runner.active() == []

    def test_dead_dispatcher_does_not_abort_the_job(self):
        def gone(_fn):
            raise RuntimeError("main thread is not in main loop")

        task = Task(dispatcher=gone)
        task.on_progress(lambda *a: None)

        def job(t):
            t.report(0.5, "rolling back")
            return "rolled back"
        task._run(job)
        assert task.result(timeout=1) == "rolled back"
