"""Imports every model so SQLAlchemy metadata (and Alembic) sees all tables."""

from app.modules.automations.models import AutomationRule, AutomationRun
from app.modules.clients.models import Client, ClientEntity, Contact
from app.modules.collaboration.models import Comment, Notification
from app.modules.files.models import FileVersion, StoredFile
from app.modules.identity.models import ApiToken, AuthSession, LoginAttempt, User
from app.modules.integrations.models import WebhookDelivery, WebhookEndpoint
from app.modules.items.models import Item, ItemMember
from app.modules.migration.models import ExternalRef, MigrationRow, MigrationRun
from app.modules.rdti.models import (
    RdtiActivity,
    RdtiAssessment,
    RdtiChecklistItem,
    RdtiChunk,
    RdtiCitation,
    RdtiClaim,
    RdtiReportSection,
)
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
from app.platform.ai_gateway.models import AiCall
from app.platform.audit.models import AuditEntry
from app.platform.commands.models import CommandLog
from app.platform.events.models import Event, EventDelivery
from app.platform.jobs.models import JobRun

__all__ = [
    "AiCall",
    "ApiToken",
    "AuditEntry",
    "AuthSession",
    "AutomationRule",
    "AutomationRun",
    "Board",
    "Client",
    "ClientEntity",
    "CommandLog",
    "Comment",
    "Contact",
    "Event",
    "EventDelivery",
    "ExternalRef",
    "FieldDefinition",
    "FileVersion",
    "FiscalYear",
    "Item",
    "ItemMember",
    "JobRun",
    "LoginAttempt",
    "LookupList",
    "LookupValue",
    "MemberRole",
    "MigrationRow",
    "MigrationRun",
    "Notification",
    "RdtiActivity",
    "RdtiAssessment",
    "RdtiChecklistItem",
    "RdtiChunk",
    "RdtiCitation",
    "RdtiClaim",
    "RdtiReportSection",
    "SavedView",
    "Status",
    "StoredFile",
    "Task",
    "TaskMember",
    "User",
    "WebhookDelivery",
    "WebhookEndpoint",
    "Workspace",
    "WorkspaceMembership",
]  # fmt: skip
