from __future__ import annotations

import uuid
from sqlalchemy import Boolean, Enum, String
from sqlalchemy.dialects.postgresql import UUID, CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base
from postgres.models.enums import GlobalRole
from postgres.models.mixins import TimestampMixin

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    global_role: Mapped[GlobalRole] = mapped_column(
        Enum(GlobalRole, name="global_role"),
        nullable = False,
        default = GlobalRole.user,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)