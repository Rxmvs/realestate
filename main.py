from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.openapi.utils import get_openapi
from sqlalchemy.orm import Session
from pwdlib import PasswordHash
from jwt.exceptions import InvalidTokenError

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
import os
import shutil

from database import engine, Base, SessionLocal
from models import User, Property
from schemas import (
    UserCreate,
    UserResponse,
    UserLogin,
    PropertyCreate,
    PropertyResponse,
    PropertyUpdate
)


# ---------------------------------------------------------------
# PAPKALAR (to'liq yo'l bilan, server qayerdan ishga tushsa ham ishlaydi)
# ---------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# uploads papkasi bo'lmasa, o'zi yaratiladi (GitHub bo'sh papkani saqlamaydi)
os.makedirs(UPLOADS_DIR, exist_ok=True)


# ---------------------------------------------------------------
# JWT SOZLAMALARI
# ---------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_SECRET_KEY")
ALGORITHM = "HS256"

if SECRET_KEY == "CHANGE_THIS_SECRET_KEY":
    print("OGOHLANTIRISH: SECRET_KEY o'rnatilmagan! Render'da Environment'ga qo'shing.")


# ---------------------------------------------------------------
# PAROL VA TOKEN SOZLAMALARI
# ---------------------------------------------------------------
password_hash = PasswordHash.recommended()
oauth2_scheme = HTTPBearer()


# ---------------------------------------------------------------
# MA'LUMOTLAR BAZASI JADVALLARI
# ---------------------------------------------------------------
Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------
# FASTAPI
# ---------------------------------------------------------------
app = FastAPI(
    title="Real Estate Platform",
    description="Ko'chmas mulk e'lonlari sayti",
    version="1.0.0"
)

app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

HAS_FRONTEND = os.path.isdir(FRONTEND_DIR)

if HAS_FRONTEND:
    app.mount(
        "/frontend",
        StaticFiles(directory=FRONTEND_DIR, html=True),
        name="frontend"
    )
else:
    print("OGOHLANTIRISH: 'frontend' papkasi topilmadi!")


# ---------------------------------------------------------------
# YORDAMCHI FUNKSIYALAR
# ---------------------------------------------------------------
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp"
}


def get_property_images(property_id: int) -> list[str]:
    """E'longa tegishli barcha rasmlar manzillarini qaytaradi."""
    images = []

    if os.path.isdir(UPLOADS_DIR):
        for filename in sorted(os.listdir(UPLOADS_DIR)):
            if filename.startswith(f"property_{property_id}_"):
                images.append(f"/uploads/{filename}")

    return images


def delete_property_images(property_id: int) -> int:
    """E'longa tegishli barcha rasmlarni o'chiradi, nechta o'chganini qaytaradi."""
    deleted_count = 0

    if os.path.isdir(UPLOADS_DIR):
        for filename in os.listdir(UPLOADS_DIR):
            if filename.startswith(f"property_{property_id}_"):
                path = os.path.join(UPLOADS_DIR, filename)

                if os.path.isfile(path):
                    os.remove(path)
                    deleted_count += 1

    return deleted_count


def build_property_response(item: Property) -> PropertyResponse:
    """E'longa egasining telefoni va rasmlarini qo'shib qaytaradi."""
    data = PropertyResponse.model_validate(item)
    data.owner_phone = item.owner.phone if item.owner else None
    data.images = get_property_images(item.id)
    return data


# ---------------------------------------------------------------
# DATABASE ULANISH
# ---------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------
# TOKENNI TEKSHIRISH
# ---------------------------------------------------------------
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("user_id")

        if user_id is None:
            raise InvalidTokenError("Token ichida user_id yo'q")

    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Token xatosi: {str(exc)}",
            headers={"WWW-Authenticate": "Bearer"}
        )

    current_user = db.query(User).filter(
        User.id == user_id
    ).first()

    if current_user is None:
        raise HTTPException(
            status_code=401,
            detail="Foydalanuvchi topilmadi!"
        )

    return current_user


# ---------------------------------------------------------------
# BOSH SAHIFA: saytga yo'naltiradi
# ---------------------------------------------------------------
@app.get("/", include_in_schema=False)
def home():
    if HAS_FRONTEND:
        return RedirectResponse(url="/frontend/")

    return {
        "message": "Real Estate loyihamiz ishga tushdi!"
    }


# ---------------------------------------------------------------
# RO'YXATDAN O'TISH: TELEFON RAQAMI ORQALI
# ---------------------------------------------------------------
@app.post("/register", response_model=UserResponse)
def register_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter(
        User.phone == user.phone
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Bu telefon raqami allaqachon ro'yxatdan o'tgan!"
        )

    new_user = User(
        name=user.name,
        phone=user.phone,
        email=None,
        password_hash=password_hash.hash(user.password)
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


# ---------------------------------------------------------------
# LOGIN: TELEFON RAQAMI ORQALI
# ---------------------------------------------------------------
@app.post("/login")
def login_user(
    user: UserLogin,
    db: Session = Depends(get_db)
):
    db_user = db.query(User).filter(
        User.phone == user.phone
    ).first()

    if not db_user or not password_hash.verify(
        user.password,
        db_user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Telefon raqami yoki parol noto'g'ri!"
        )

    access_token = jwt.encode(
        {
            "user_id": db_user.id,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=60)
        },
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return {
        "message": "Tizimga muvaffaqiyatli kirdingiz!",
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": db_user.id,
            "name": db_user.name,
            "phone": db_user.phone,
            "role": db_user.role
        }
    }


# ---------------------------------------------------------------
# SHAXSIY KABINET
# ---------------------------------------------------------------
@app.get("/profile", response_model=UserResponse)
def get_profile(
    current_user: User = Depends(get_current_user)
):
    return current_user


# ---------------------------------------------------------------
# E'LON YARATISH
# ---------------------------------------------------------------
@app.post("/properties", response_model=PropertyResponse)
def create_property(
    property_data: PropertyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    new_property = Property(
        **property_data.model_dump(),
        user_id=current_user.id
    )

    db.add(new_property)
    db.commit()
    db.refresh(new_property)

    return build_property_response(new_property)


# ---------------------------------------------------------------
# BARCHA E'LONLARNI RASMLARI BILAN KO'RISH
# ---------------------------------------------------------------
@app.get("/properties", response_model=list[PropertyResponse])
def get_properties(
    db: Session = Depends(get_db)
):
    properties = db.query(Property).filter(
        Property.status == "active"
    ).order_by(Property.created_at.desc()).all()

    return [build_property_response(item) for item in properties]


# ---------------------------------------------------------------
# MENING E'LONLARIM (endi rasmlari va telefon bilan)
# ---------------------------------------------------------------
@app.get("/my-properties", response_model=list[PropertyResponse])
def get_my_properties(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    properties = db.query(Property).filter(
        Property.user_id == current_user.id
    ).order_by(Property.created_at.desc()).all()

    return [build_property_response(item) for item in properties]


# ---------------------------------------------------------------
# E'LONNI TAHRIRLASH
# ---------------------------------------------------------------
@app.put("/properties/{property_id}", response_model=PropertyResponse)
def update_property(
    property_id: int,
    property_data: PropertyUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    property_item = db.query(Property).filter(
        Property.id == property_id,
        Property.user_id == current_user.id
    ).first()

    if property_item is None:
        raise HTTPException(
            status_code=404,
            detail="E'lon topilmadi yoki sizga tegishli emas!"
        )

    update_data = property_data.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(property_item, key, value)

    db.commit()
    db.refresh(property_item)

    return build_property_response(property_item)


# ---------------------------------------------------------------
# E'LONNI O'CHIRISH (rasmlari ham o'chadi)
# ---------------------------------------------------------------
@app.delete("/properties/{property_id}")
def delete_property(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    property_item = db.query(Property).filter(
        Property.id == property_id,
        Property.user_id == current_user.id
    ).first()

    if property_item is None:
        raise HTTPException(
            status_code=404,
            detail="E'lon topilmadi yoki sizga tegishli emas!"
        )

    db.delete(property_item)
    db.commit()

    delete_property_images(property_id)

    return {
        "message": "E'lon muvaffaqiyatli o'chirildi!"
    }


# ---------------------------------------------------------------
# BITTA E'LONNI RASMLARI BILAN KO'RISH
# ---------------------------------------------------------------
@app.get("/properties/{property_id}", response_model=PropertyResponse)
def get_property(
    property_id: int,
    db: Session = Depends(get_db)
):
    property_item = db.query(Property).filter(
        Property.id == property_id,
        Property.status == "active"
    ).first()

    if property_item is None:
        raise HTTPException(
            status_code=404,
            detail="E'lon topilmadi!"
        )

    return build_property_response(property_item)


# ---------------------------------------------------------------
# E'LONLARNI QIDIRISH VA FILTRLASH (endi rasmlari va telefon bilan)
# ---------------------------------------------------------------
@app.get("/search-properties", response_model=list[PropertyResponse])
def search_properties(
    address: Optional[str] = None,
    listing_type: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    rooms: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Property).filter(
        Property.status == "active"
    )

    if address:
        query = query.filter(
            Property.address.ilike(f"%{address}%")
        )

    if listing_type:
        query = query.filter(
            Property.listing_type == listing_type
        )

    if min_price is not None:
        query = query.filter(
            Property.price >= min_price
        )

    if max_price is not None:
        query = query.filter(
            Property.price <= max_price
        )

    if rooms is not None:
        query = query.filter(
            Property.rooms == rooms
        )

    properties = query.order_by(
        Property.created_at.desc()
    ).all()

    return [build_property_response(item) for item in properties]


# ---------------------------------------------------------------
# E'LON RASMINI ALMASHTIRISH
# ---------------------------------------------------------------
@app.put("/properties/{property_id}/replace-image")
def replace_property_image(
    property_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    property_item = db.query(Property).filter(
        Property.id == property_id,
        Property.user_id == current_user.id
    ).first()

    if not property_item:
        raise HTTPException(
            status_code=404,
            detail="E'lon topilmadi yoki sizga tegishli emas"
        )

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Faqat JPG, PNG yoki WEBP rasm yuklash mumkin"
        )

    os.makedirs(UPLOADS_DIR, exist_ok=True)

    # Shu e'longa tegishli eski rasmlarni o'chirish
    delete_property_images(property_id)

    # Yangi rasmni saqlash
    filename = (
        f"property_{property_id}_{datetime.now().timestamp()}"
        f"{ALLOWED_IMAGE_TYPES[file.content_type]}"
    )

    file_path = os.path.join(UPLOADS_DIR, filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "message": "Rasm muvaffaqiyatli almashtirildi",
        "filename": filename,
        "file_path": f"/uploads/{filename}"
    }


# ---------------------------------------------------------------
# E'LON RASMINI O'CHIRISH
# ---------------------------------------------------------------
@app.delete("/properties/{property_id}/delete-image")
def delete_property_image(
    property_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    property_item = db.query(Property).filter(
        Property.id == property_id,
        Property.user_id == current_user.id
    ).first()

    if not property_item:
        raise HTTPException(
            status_code=404,
            detail="E'lon topilmadi yoki sizga tegishli emas"
        )

    deleted_count = delete_property_images(property_id)

    if deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Bu e'lon uchun rasm topilmadi"
        )

    return {
        "message": "Rasm muvaffaqiyatli o'chirildi",
        "deleted_count": deleted_count
    }


# ---------------------------------------------------------------
# E'LON UCHUN BIR NECHTA RASM YUKLASH
# ---------------------------------------------------------------
@app.post("/properties/{property_id}/upload-images")
def upload_multiple_images(
    property_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    property_item = db.query(Property).filter(
        Property.id == property_id,
        Property.user_id == current_user.id
    ).first()

    if not property_item:
        raise HTTPException(
            status_code=404,
            detail="E'lon topilmadi yoki sizga tegishli emas"
        )

    if len(files) > 10:
        raise HTTPException(
            status_code=400,
            detail="Bir martada ko'pi bilan 10 ta rasm yuklash mumkin"
        )

    for file in files:
        if file.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail="Faqat JPG, PNG yoki WEBP rasmlar mumkin"
            )

    os.makedirs(UPLOADS_DIR, exist_ok=True)

    uploaded_files = []

    for index, file in enumerate(files):
        filename = (
            f"property_{property_id}_"
            f"{datetime.now().timestamp()}_{index}"
            f"{ALLOWED_IMAGE_TYPES[file.content_type]}"
        )

        file_path = os.path.join(UPLOADS_DIR, filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        uploaded_files.append(filename)

    return {
        "message": "Rasmlar muvaffaqiyatli yuklandi",
        "uploaded_count": len(uploaded_files),
        "files": uploaded_files
    }


# ---------------------------------------------------------------
# E'LON RASMLARINI TO'LIQ ALMASHTIRISH
# ---------------------------------------------------------------
@app.put("/properties/{property_id}/replace-images")
def replace_property_images(
    property_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    property_item = db.query(Property).filter(
        Property.id == property_id,
        Property.user_id == current_user.id
    ).first()

    if not property_item:
        raise HTTPException(
            status_code=404,
            detail="E'lon topilmadi yoki sizga tegishli emas"
        )

    if len(files) < 1 or len(files) > 10:
        raise HTTPException(
            status_code=400,
            detail="1 tadan 10 tagacha rasm tanlang"
        )

    for file in files:
        if file.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail="Faqat JPG, PNG yoki WEBP rasmlar mumkin"
            )

    os.makedirs(UPLOADS_DIR, exist_ok=True)

    uploaded_files = []

    try:
        for index, file in enumerate(files):
            filename = (
                f"property_{property_id}_"
                f"{datetime.now().timestamp()}_{index}"
                f"{ALLOWED_IMAGE_TYPES[file.content_type]}"
            )

            file_path = os.path.join(UPLOADS_DIR, filename)

            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            uploaded_files.append(filename)

        # Yangi rasmlar muvaffaqiyatli saqlangandan keyin eskilarini o'chirish
        for filename in os.listdir(UPLOADS_DIR):
            if filename.startswith(f"property_{property_id}_"):
                old_path = os.path.join(UPLOADS_DIR, filename)

                if os.path.isfile(old_path) and filename not in uploaded_files:
                    os.remove(old_path)

    except Exception:
        for filename in uploaded_files:
            path = os.path.join(UPLOADS_DIR, filename)
            if os.path.exists(path):
                os.remove(path)

        raise HTTPException(
            status_code=500,
            detail="Rasmlarni almashtirishda xatolik yuz berdi"
        )

    return {
        "message": "Rasmlar muvaffaqiyatli almashtirildi",
        "uploaded_count": len(uploaded_files),
        "files": uploaded_files
    }


# ---------------------------------------------------------------
# SWAGGER UCHUN RASMLARNI YUKLASH SOZLAMASI
# ---------------------------------------------------------------
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    try:
        schema = openapi_schema["paths"][
            "/properties/{property_id}/upload-images"
        ]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]

        schema_name = schema["$ref"].split("/")[-1]

        openapi_schema["components"]["schemas"][schema_name]["properties"]["files"] = {
            "type": "array",
            "items": {
                "type": "string",
                "format": "binary"
            },
            "title": "Files"
        }
    except (KeyError, TypeError):
        # Swagger sozlamasi ishlamasa ham sayt to'xtab qolmasin
        pass

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
