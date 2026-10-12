"""Business modules.

Each module registers its commands (and optionally event subscribers and
scheduled jobs) on import. ``load_modules`` is the single place that decides
which modules run; adding a feature module = adding it to ``ENABLED``.
"""

import importlib

ENABLED = [
    "identity",
    "workspaces",
    "clients",
    "items",
    "tasks",
    "views",
    "collaboration",
    "activity",
    "automations",
    "migration",
    "system",
]

# Optional sub-modules a feature module may provide.
_PARTS = ("commands", "subscribers", "jobs")

_loaded = False


def load_modules() -> None:
    global _loaded
    if _loaded:
        return
    for name in ENABLED:
        for part in _PARTS:
            try:
                importlib.import_module(f"app.modules.{name}.{part}")
            except ModuleNotFoundError as e:
                if e.name != f"app.modules.{name}.{part}":
                    raise
    _loaded = True
