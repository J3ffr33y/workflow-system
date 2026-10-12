import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin
from app.platform.audit.models import Audited


class SavedView(IdMixin, TimestampMixin, Audited, Base):
    """Column layout, filters and sort for a board.

    ``config``: {"columns": [{"key", "width", "hidden", "pinned"}],
                 "filter": <filter tree>, "sort": [{"field", "dir"}],
                 "search": str | null, "group_by": str | null}
    ``board_id`` NULL means the view applies to every board in the workspace.
    """

    __tablename__ = "saved_views"
    __entity_type__ = "saved_view"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    board_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("boards.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    scope: Mapped[str] = mapped_column(String(10), default="personal")  # personal | shared
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
