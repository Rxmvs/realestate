
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    DateTime,
    ForeignKey
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


# 1. FOYDALANUVCHILAR JADVALI
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(150), nullable=False)

    # Eski foydalanuvchilar uchun email saqlanadi,
    # yangi ro'yxatdan o'tishda majburiy emas.
    email = Column(String(255), unique=True, index=True, nullable=True)

    password_hash = Column(String(255), nullable=False)

    # Telefon raqami takrorlanmasligi kerak.
    phone = Column(String(30), unique=True, index=True, nullable=True)

    role = Column(String(30), default="user", nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    properties = relationship(
        "Property",
        back_populates="owner"
    )


# 2. KO'CHMAS MULK E'LONLARI JADVALI
class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    type = Column(String(50), nullable=False)
    listing_type = Column(String(50), nullable=False)

    price = Column(Float, nullable=False)
    currency = Column(String(10), default="UZS", nullable=False)

    rooms = Column(Integer, nullable=True)
    area = Column(Float, nullable=True)

    floor = Column(Integer, nullable=True)
    total_floors = Column(Integer, nullable=True)

    address = Column(String(500), nullable=False)

    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    status = Column(String(30), default="active", nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    owner = relationship(
        "User",
        back_populates="properties"
    )
