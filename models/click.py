from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from database import Base


class Click(Base):
    __tablename__ = "clicks"

    id = Column(Integer, primary_key=True, index=True)

    url_id = Column(
        Integer,
        ForeignKey("urls.id"),
        nullable=False
    )

    ip_address = Column(String, nullable=True)

    user_agent = Column(String, nullable=True)

    is_monetized = Column(
        Boolean,
        default=False
    )

    clicked_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )