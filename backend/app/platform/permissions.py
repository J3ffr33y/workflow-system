"""Roles, permission points and the actor model.

Permissions are checked in exactly two places: the command bus (writes) and
query entry points (reads). Routers never decide authorisation themselves;
the frontend only hides buttons using the permission list from /api/me.
"""

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from app.core.errors import PermissionDenied


class WorkspaceRole(StrEnum):
    VIEWER = "viewer"
    MEMBER = "member"
    MANAGER = "manager"
    ADMIN = "admin"


# Permission points. Keep the list flat and string-based so a future
# "custom roles" table can store them without code changes.
P_ITEMS_READ = "items.read"
P_ITEMS_CREATE = "items.create"
P_ITEMS_UPDATE = "items.update"
P_ITEMS_ARCHIVE = "items.archive"
P_ITEMS_DELETE = "items.delete"
P_ITEMS_ROLLOVER = "items.rollover"
P_TASKS_WRITE = "tasks.write"
P_COMMENTS_WRITE = "comments.write"
P_VIEWS_PERSONAL = "views.personal"
P_VIEWS_SHARED = "views.shared"
P_EXPORT = "items.export"
P_CLIENTS_READ = "clients.read"
P_CLIENTS_WRITE = "clients.write"
P_CLIENTS_ARCHIVE = "clients.archive"
P_CLIENTS_DELETE = "clients.delete"
P_AUDIT_VIEW_VALUES = "audit.view_values"
P_AUDIT_REVERT = "audit.revert"
P_AUTOMATIONS_MANAGE = "automations.manage"
P_BOARDS_MANAGE = "boards.manage"
P_SCHEMA_MANAGE = "schema.manage"  # fields, statuses, roles, lookups
P_MIGRATION_RUN = "migration.run"
P_USERS_MANAGE = "users.manage"  # superadmin only
P_SYSTEM_ADMIN = "system.admin"  # superadmin only

_VIEWER = {P_ITEMS_READ, P_CLIENTS_READ}
_MEMBER = _VIEWER | {
    P_ITEMS_CREATE,
    P_ITEMS_UPDATE,
    P_ITEMS_ARCHIVE,
    P_ITEMS_ROLLOVER,
    P_TASKS_WRITE,
    P_COMMENTS_WRITE,
    P_VIEWS_PERSONAL,
    P_EXPORT,
    P_CLIENTS_WRITE,
    P_AUDIT_REVERT,
}
_MANAGER = _MEMBER | {
    P_ITEMS_DELETE,
    P_VIEWS_SHARED,
    P_CLIENTS_ARCHIVE,
    P_CLIENTS_DELETE,
    P_AUDIT_VIEW_VALUES,
    P_AUTOMATIONS_MANAGE,
}
_ADMIN = _MANAGER | {P_BOARDS_MANAGE, P_SCHEMA_MANAGE, P_MIGRATION_RUN}

ROLE_PERMISSIONS: dict[WorkspaceRole, frozenset[str]] = {
    WorkspaceRole.VIEWER: frozenset(_VIEWER),
    WorkspaceRole.MEMBER: frozenset(_MEMBER),
    WorkspaceRole.MANAGER: frozenset(_MANAGER),
    WorkspaceRole.ADMIN: frozenset(_ADMIN),
}
SUPERADMIN_ONLY = frozenset({P_USERS_MANAGE, P_SYSTEM_ADMIN})


class ActorKind(StrEnum):
    USER = "user"
    SYSTEM = "system"  # scheduled jobs, bootstrap
    AUTOMATION = "automation"
    MIGRATION = "migration"


@dataclass(frozen=True)
class Actor:
    kind: ActorKind
    user_id: uuid.UUID | None
    display: str
    is_superadmin: bool = False
    roles: dict[uuid.UUID, WorkspaceRole] = field(default_factory=dict)

    @property
    def is_privileged(self) -> bool:
        """System-level actors act with full rights; their *triggering* user
        was already authorised when the rule or migration was created."""
        return self.is_superadmin or self.kind in (
            ActorKind.SYSTEM,
            ActorKind.AUTOMATION,
            ActorKind.MIGRATION,
        )

    def permissions_in(self, workspace_id: uuid.UUID) -> frozenset[str]:
        if self.is_privileged:
            return frozenset().union(*ROLE_PERMISSIONS.values()) | SUPERADMIN_ONLY
        role = self.roles.get(workspace_id)
        return ROLE_PERMISSIONS[role] if role else frozenset()

    def can(self, permission: str, workspace_id: uuid.UUID | None = None) -> bool:
        if self.is_privileged:
            return True
        if permission in SUPERADMIN_ONLY:
            return False
        if workspace_id is None:
            # Global resources (clients, users list): any workspace granting it.
            return any(permission in ROLE_PERMISSIONS[r] for r in self.roles.values())
        return permission in self.permissions_in(workspace_id)

    def require(self, permission: str, workspace_id: uuid.UUID | None = None) -> None:
        if not self.can(permission, workspace_id):
            raise PermissionDenied(f"missing permission {permission}", details={"permission": permission})

    def workspace_ids(self) -> set[uuid.UUID] | None:
        """Workspaces this actor may read; None means all."""
        return None if self.is_privileged else set(self.roles)


SYSTEM_ACTOR = Actor(kind=ActorKind.SYSTEM, user_id=None, display="System")
