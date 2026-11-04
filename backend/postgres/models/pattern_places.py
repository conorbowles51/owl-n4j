"""A named place of the Patterns screen (04 sections 7.7 and 8.3): the ORM view the case decision ledger needs as a
subject. The table is written by ``services.pattern_of_life.routine.name_place``."""
from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base


class PolPlaceCluster(Base):
    __tablename__ = "pol_place_cluster"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"),
                                               nullable=False)
    subject_key: Mapped[str] = mapped_column(String(80), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    radius_m: Mapped[float] = mapped_column(Float, nullable=False)
    stay_count: Mapped[int] = mapped_column(Integer, nullable=False)
    day_count: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    label_decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    label_by_name: Mapped[str | None] = mapped_column(Text, nullable=True)
