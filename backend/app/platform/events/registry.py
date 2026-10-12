"""Event subscribers.

A subscriber is a named function that runs in the worker for every event
whose type matches one of its patterns. Patterns support a trailing ``*``
("item.*"). Subscribers must be idempotent: deliveries are at-least-once.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatchcase
from typing import Any


@dataclass(frozen=True)
class EventRecord:
    id: int
    type: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    workspace_id: uuid.UUID | None
    command_id: uuid.UUID | None
    origin: str
    actor_id: uuid.UUID | None
    depth: int
    payload: dict[str, Any]
    occurred_at: datetime


SubscriberFn = Callable[[EventRecord], None]


@dataclass(frozen=True)
class Subscriber:
    name: str
    patterns: tuple[str, ...]
    handler: SubscriberFn
    max_attempts: int = 8

    def matches(self, event_type: str) -> bool:
        return any(fnmatchcase(event_type, p) for p in self.patterns)


@dataclass
class SubscriberRegistry:
    subscribers: dict[str, Subscriber] = field(default_factory=dict)

    def register(self, sub: Subscriber) -> None:
        if sub.name in self.subscribers:
            raise ValueError(f"duplicate subscriber {sub.name}")
        self.subscribers[sub.name] = sub

    def for_event(self, event_type: str) -> list[Subscriber]:
        return [s for s in self.subscribers.values() if s.matches(event_type)]


subscribers = SubscriberRegistry()
