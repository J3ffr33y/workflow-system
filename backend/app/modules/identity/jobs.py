from datetime import timedelta

from app.modules.identity.commands import PurgeExpiredSessions
from app.platform.commands import Origin, bus
from app.platform.jobs.scheduler import scheduled
from app.platform.permissions import SYSTEM_ACTOR


@scheduled("identity.purge_sessions", every=timedelta(days=1))
def purge_sessions() -> str:
    n = bus.execute(PurgeExpiredSessions(), actor=SYSTEM_ACTOR, origin=Origin.SYSTEM).result
    return f"purged {n} expired sessions"
