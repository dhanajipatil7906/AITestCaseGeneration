import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    total_files: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    total_lines: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    language_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    function_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    class_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    summary: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
