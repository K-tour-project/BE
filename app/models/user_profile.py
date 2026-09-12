"""Optional profile image, owned by the authenticated user."""
from __future__ import annotations

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True, autoincrement=False,
    )
    profile_image_url: Mapped[str] = mapped_column(Text)
    user: Mapped["User"] = relationship("User", back_populates="profile")
