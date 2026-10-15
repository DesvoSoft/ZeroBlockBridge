"""UI-agnostic API over the core (docs/ARCHITECTURE.md, "API seam").

UIs import from here, never from app.core / app.services directly for
actions or state. This package never imports a GUI toolkit.
"""

from app.api.app_api import AppApi
from app.api.events import Dispatcher, EventHub, Subscription, direct
from app.api.servers import MemorySample, NoServerJarError, ServerInfo, ServerRunningError
from app.api.tasks import Task
from app.core.server_events import ServerEvent

__all__ = [
    "AppApi", "Dispatcher", "EventHub", "MemorySample", "NoServerJarError", "ServerEvent",
    "ServerInfo", "ServerRunningError", "Subscription", "Task", "direct",
]
