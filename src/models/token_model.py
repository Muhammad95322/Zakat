"""Model Token (verifikasi email, reset password, refresh token)."""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator, String as SAString

from src.database import Base


class UUIDType(TypeDecorator):
    """UUID yang kompatibel dengan SQLite dan PostgreSQL."""
    impl = SAString(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return str(value)


class Token(Base):
    """Token untuk verifikasi, reset password, dan refresh."""

    __tablename__ = "tokens"

    id = Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUIDType, ForeignKey("users.id"), nullable=False)
    jenis = Column(
        Enum("verifikasi_email", "reset_password", "refresh", name="token_jenis_enum"),
        nullable=False,
    )
    token_hash = Column(String(255), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="tokens")

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    @property
    def is_valid(self) -> bool:
        return not self.is_expired and not self.is_used

    def __repr__(self) -> str:
        return f"<Token id={self.id} jenis='{self.jenis}' user_id={self.user_id}>"
