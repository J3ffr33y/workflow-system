"""Imports every model so SQLAlchemy metadata (and Alembic) sees all tables."""

from app.modules.automations.models import AutomationRule, AutomationRun
from app.modules.clients.models import Client, ClientEntity, Contact
from app.modules.collaboration.models import Comment, Notification
from app.modules.identity.models import AuthSession, LoginAttempt, User
from app.modules.items.models import Item, ItemMember
from app.modules.migration.models import ExternalRef, MigrationRow, MigrationRun
from app.modules.tasks.models import Task, TaskMember
from app.modules.views.models import SavedView
from app.modules.workspaces.models import (
    Board,
    FieldDefinition,
    FiscalYear,
    LookupList,
    LookupValue,
    MemberRole,
    Status,
    Workspace,
    WorkspaceMembership,
)
from app.platform.audit.models import AuditEntry
from app.platform.commands.models import CommandLog
from app.platform.events.models import Event, EventDelivery
from app.platform.jobs.models import JobRun

__all__ = [
    "AuditEntry", "AuthSession", "AutomationRule", "AutomationRun", "Board", "Client",
    "ClientEntity", "CommandLog", "Comment", "Contact", "Event", "EventDelivery",
    "ExternalRef", "FieldDefinition", "FiscalYear", "Item", "ItemMember", "JobRun",
    "LoginAttempt", "LookupList", "LookupValue", "MemberRole", "MigrationRow",
    "MigrationRun", "Notification", "SavedView", "Status", "Task", "TaskMember",
    "User", "Workspace", "WorkspaceMembership",
]  # fmt: skip
