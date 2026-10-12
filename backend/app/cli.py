"""Operational commands.

python -m app.cli bootstrap        # reference config + first admin (idempotent)
python -m app.cli demo-users       # sample team for local testing
python -m app.cli run-job <name>   # run a scheduled job now
"""

import argparse
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import read_session
from app.modules import load_modules
from app.modules.identity.commands import CreateUser
from app.modules.identity.models import User
from app.platform.commands import Origin, bus
from app.platform.permissions import SYSTEM_ACTOR


def bootstrap() -> None:
    from app.seed import seed_reference_config

    ids = seed_reference_config()
    settings = get_settings()
    email = settings.bootstrap_admin_email.lower()
    with read_session() as s:
        exists = s.scalar(select(User.id).where(User.email == email))
    if not exists:
        bus.execute(
            CreateUser(
                email=email,
                full_name="Administrator",
                password=settings.bootstrap_admin_password.get_secret_value(),
                is_superadmin=True,
                memberships={k: "admin" for k in ids},  # type: ignore[misc]
            ),
            actor=SYSTEM_ACTOR,
            origin=Origin.SYSTEM,
        )
        print(f"created admin {email}")
    print("bootstrap complete:", ", ".join(ids))


DEMO_TEAM = [
    ("cathy@demo.local", "Cathy Lau", ["CL", "Cathy"], {"accounting": "admin", "grants": "manager"}),
    ("jean@demo.local", "Jean Ren", [], {"accounting": "manager"}),
    ("jenny@demo.local", "Jenny Li", [], {"accounting": "manager"}),
    ("violet@demo.local", "Violet Ma", [], {"accounting": "member"}),
    ("joe@demo.local", "Joe Liu", [], {"accounting": "member"}),
    ("eva@demo.local", "Eva Ren", [], {"accounting": "member"}),
    ("win@demo.local", "Win Yang", ["Win"], {"grants": "member"}),
    ("fish@demo.local", "Fish Zhou", ["Fish"], {"grants": "member"}),
    ("grace@demo.local", "Grace Gao", [], {"grants": "member"}),
]


def demo_users(password: str) -> None:
    with read_session() as s:
        existing = set(s.scalars(select(User.email)))
    for email, name, aliases, memberships in DEMO_TEAM:
        if email in existing:
            continue
        bus.execute(
            CreateUser(
                email=email, full_name=name, password=password, aliases=aliases, memberships=memberships
            ),  # type: ignore[arg-type]
            actor=SYSTEM_ACTOR,
            origin=Origin.SYSTEM,
        )
        print("created", email)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("bootstrap")
    d = sub.add_parser("demo-users")
    d.add_argument("--password", default="Demo-pass-2026")
    j = sub.add_parser("run-job")
    j.add_argument("name")
    args = parser.parse_args(argv)
    load_modules()
    if args.cmd == "bootstrap":
        bootstrap()
    elif args.cmd == "demo-users":
        demo_users(args.password)
    elif args.cmd == "run-job":
        from app.platform.jobs.scheduler import jobs, run_job

        job = next((j for j in jobs() if j.name == args.name), None)
        if job is None:
            print("unknown job; available:", ", ".join(j.name for j in jobs()))
            return 1
        run_job(job, force=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
