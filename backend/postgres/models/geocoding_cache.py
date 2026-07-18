from datetime import datetime

from sqlalchemy import DateTime, Float, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base


JSON_DOCUMENT = JSONB().with_variant(JSON(), "sqlite")


class GeocodingCacheEntry(Base):
    __tablename__ = "geocoding_cache"

    provider: Mapped[str] = mapped_column(String(64), primary_key=True)
    normalized_query: Mapped[str] = mapped_column(Text, primary_key=True)
    original_query: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geocoder: Mapped[str | None] = mapped_column(String(64), nullable=True)
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    formatted_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    precision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    candidates: Mapped[list | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
