"""Runs an import row by row. Each row is its own command (one bad row never
blocks the rest) sharing the run's batch id (so the run can be rolled back)."""

import uuid
from typing import Any

from sqlalchemy import select

from app.core.db import read_session
from app.core.errors import AppError
from app.modules.migration.commands import FinishRun, ImportRow, MarkRowError
from app.modules.migration.models import MigrationRow, MigrationRun
from app.platform.commands import Origin, bus
from app.platform.permissions import Actor, ActorKind


def migration_actor(run: MigrationRun) -> Actor:
    return Actor(kind=ActorKind.MIGRATION, user_id=run.created_by, display=f"Migration: {run.name}"[:200])


def commit_run(run_id: uuid.UUID) -> dict[str, Any]:
    with read_session() as s:
        run = s.get(MigrationRun, run_id)
        if run is None:
            raise ValueError("run not found")
        row_ids = list(
            s.scalars(
                select(MigrationRow.id)
                .where(MigrationRow.run_id == run_id, MigrationRow.outcome.is_(None))
                .order_by(MigrationRow.row_no)
            )
        )
    actor = migration_actor(run)
    for rid in row_ids:
        try:
            bus.execute(
                ImportRow(run_id=run_id, row_id=rid),
                actor=actor,
                origin=Origin.MIGRATION,
                batch_id=run.batch_id,
                idempotency_key=f"mig:{run_id}:{rid}",
            )
        except Exception as e:
            msg = e.message if isinstance(e, AppError) else repr(e)
            if isinstance(e, AppError) and e.details:
                msg = f"{msg}: {e.details}"
            bus.execute(
                MarkRowError(run_id=run_id, row_id=rid, message=msg), actor=actor, origin=Origin.MIGRATION
            )
    return bus.execute(FinishRun(run_id=run_id), actor=actor, origin=Origin.MIGRATION).result  # type: ignore[no-any-return]
