import os
import uuid
from collections.abc import Iterator
from typing import Any

os.environ.setdefault("FLOW_DATABASE_URL", "postgresql+psycopg://flow:flow@localhost:5432/flow_test")
os.environ.setdefault("FLOW_ENV", "test")

import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command
from app.core.config import get_settings
from app.core.db import read_session, reset_engines, write_engine
from app.modules import load_modules
from app.modules.identity.commands import CreateUser
from app.modules.identity.models import User
from app.modules.identity.queries import actor_for_user
from app.platform.commands import Command, CommandResult, Origin, bus
from app.platform.permissions import SYSTEM_ACTOR, Actor

BACKEND = os.path.dirname(os.path.dirname(__file__))


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    assert "flow_test" in get_settings().database_url, "tests must run against the test database"
    reset_engines()
    with write_engine().begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND, "alembic"))
    command.upgrade(cfg, "head")
    load_modules()
    yield
    reset_engines()


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    yield
    with write_engine().begin() as conn:
        tables = (
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'"
                )
            )
            .scalars()
            .all()
        )
        conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"))


def run(cmd: Command, actor: Actor = SYSTEM_ACTOR, **kw: Any) -> Any:
    return bus.execute(cmd, actor=actor, origin=kw.pop("origin", Origin.UI), **kw).result


def run_full(cmd: Command, actor: Actor = SYSTEM_ACTOR, **kw: Any) -> CommandResult:
    return bus.execute(cmd, actor=actor, origin=kw.pop("origin", Origin.UI), **kw)


@pytest.fixture
def seeded() -> dict[str, str]:
    from app.seed import seed_reference_config

    return seed_reference_config()


def make_user(
    email: str = "user@example.com",
    name: str = "Test User",
    memberships: dict[str, str] | None = None,
    superadmin: bool = False,
    aliases: list[str] | None = None,
) -> Actor:
    uid = run(
        CreateUser(
            email=email,
            full_name=name,
            password="Sup3r-secret-pw",
            is_superadmin=superadmin,
            memberships=memberships or {},  # type: ignore[arg-type]
            aliases=aliases or [],
        )
    )["id"]
    with read_session() as s:
        user = s.get(User, uuid.UUID(uid))
        assert user is not None
        return actor_for_user(s, user)
