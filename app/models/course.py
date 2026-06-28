"""courses / course_places — 사용자 저장 코스와 경유지. 최소 컬럼.

이동수단·총거리/시간·공유(is_public)·다일(day)·체류/이동시간은 그 기능 붙일 때 추가.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import CreatedAtMixin


class Course(Base, CreatedAtMixin):
    __tablename__ = "courses"

    course_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="courses")  # noqa: F821
    items: Mapped[list["CoursePlace"]] = relationship(
        "CoursePlace",
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="CoursePlace.visit_order",
    )


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
    visit_order: Mapped[int] = mapped_column(Integer, nullable=False)

    course: Mapped["Course"] = relationship("Course", back_populates="items")
    place: Mapped["Place"] = relationship("Place")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("course_id", "visit_order", name="uq_course_places_order"),
    )
