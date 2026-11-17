
from typing import Optional
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# FOYDALANUVCHI
class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    phone: str = Field(min_length=7, max_length=30)
    password: str = Field(min_length=8)


class UserResponse(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# TIZIMGA KIRISH
class UserLogin(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    password: str = Field(min_length=8)


# E'LON YARATISH
class PropertyCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: Optional[str] = None

    type: str
    listing_type: str

    price: float = Field(gt=0)
    currency: str = "UZS"

    rooms: Optional[int] = Field(default=None, ge=1)
    area: Optional[float] = Field(default=None, gt=0)

    floor: Optional[int] = Field(default=None, ge=1)
    total_floors: Optional[int] = Field(default=None, ge=1)

    address: str
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)


# E'LONNI QAYTARISH
class PropertyResponse(BaseModel):
    id: int
    user_id: int
    owner_phone: Optional[str] = None

    title: str
    description: Optional[str] = None

    type: str
    listing_type: str

    price: float
    currency: str

    rooms: Optional[int] = None
    area: Optional[float] = None

    floor: Optional[int] = None
    total_floors: Optional[int] = None

    address: str
    images: list[str] = Field(default_factory=list)

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    status: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# E'LONNI TAHRIRLASH
class PropertyUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=255)
    description: Optional[str] = None
    type: Optional[str] = None
    listing_type: Optional[str] = None
    price: Optional[float] = Field(default=None, gt=0)
    currency: Optional[str] = None
    rooms: Optional[int] = Field(default=None, ge=1)
    area: Optional[float] = Field(default=None, gt=0)
    floor: Optional[int] = Field(default=None, ge=1)
    total_floors: Optional[int] = Field(default=None, ge=1)
    address: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
