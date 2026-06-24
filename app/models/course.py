"""courses / course_places — 사용자가 만든 관광 동선과 경유지.

⚠️ §3.5(위치기반서비스 회피): 출발지 등을 raw GPS 좌표로 저장하지 않는다.
   경유지는 place_id로만 참조한다(좌표는 places.geom = 큐레이션 좌표를 사용).
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import TimestampMixin, TransportMode


class Course(Base, TimestampMixin):
    __tablename__ = "courses"

    course_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    transport_mode: Mapped[TransportMode] = mapped_column(
        SAEnum(TransportMode, name="transport_mode"),
        server_default=text("'transit'"),
        nullable=False,
    )
    total_distance_m: Mapped[int | None] = mapped_column(Integer)
    total_duration_min: Mapped[int | None] = mapped_column(Integer)
    is_public: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )  # 공유 여부(다른 사용자가 보고 '좋아요' 가능)

    user: Mapped["User"] = relationship("User", back_populates="courses")  # noqa: F821
    items: Mapped[list["CoursePlace"]] = relationship(
        "CoursePlace",
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="CoursePlace.visit_order",
    )

    __table_args__ = (Index("ix_courses_user_id", "user_id"),)


class CoursePlace(Base):
    __tablename__ = "course_places"

    course_place_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.course_id", ondelete="CASCADE"), nullable=False
    )
    # 코스에 담긴 장소는 함부로 지워지면 안 되므로 RESTRICT.
    place_id: Mapped[int] = mapped_column(
        ForeignKey("places.place_id", ondelete="RESTRICT"), nullable=False
    )
    day: Mapped[int] = mapped_column(
        SmallInteger, server_default=text("1"), nullable=False
    )  # 며칠차(1박2일이면 1 또는 2). visit_order는 코스 전체 통합 순번.
    visit_order: Mapped[int] = mapped_column(Integer, nullable=False)
    stay_minutes: Mapped[int | None] = mapped_column(Integer)
    travel_to_next_min: Mapped[int | None] = mapped_column(Integer)

    course: Mapped["Course"] = relationship("Course", back_populates="items")
    place: Mapped["Place"] = relationship("Place")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("course_id", "visit_order", name="uq_course_places_order"),
        Index("ix_course_places_course_id", "course_id"),
    )
