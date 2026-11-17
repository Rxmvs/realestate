from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pwdlib import PasswordHash
from jwt.exceptions import InvalidTokenError
from fastapi.openapi.utils import get_openapi

from datetime import datetime, timedelta, timezone

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


# JWT SOZLAMALARI
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_SECRET_KEY")
ALGORITHM = "HS256"


# PAROL VA TOKEN SOZLAMALARI
password_hash = PasswordHash.recommended()
oauth2_scheme = HTTPBearer()


# MA'LUMOTLAR BAZASI JADVALLARI
Base.metadata.create_all(bind=engine)


# FASTAPI
app = FastAPI(
    title="Real Estate Platform",
    description="Ko'chmas mulk e'lonlari sayti",
    version="1.0.0"
)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/frontend", StaticFiles(directory="frontend", html=True), name="frontend")


# DATABASE ULANISH
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# TOKENNI TEKSHIRISH
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


# BOSH SAHIFA
@app.get("/")
def home():
    return {
        "message": "Real Estate loyihamiz ishga tushdi!"
    }


# RO'YXATDAN O'TISH — TELEFON RAQAMI ORQALI
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


# LOGIN — TELEFON RAQAMI ORQALI
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


# SHAXSIY KABINET
@app.get("/profile", response_model=UserResponse)
def get_profile(
    current_user: User = Depends(get_current_user)
):
    return current_user


# E'LON YARATISH
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

    return new_property


# BARCHA E'LONLARNI RASMLARI BILAN KO'RISH
@app.get("/properties", response_model=list[PropertyResponse])
def get_properties(
    db: Session = Depends(get_db)
):
    properties = db.query(Property).filter(
        Property.status == "active"
    ).order_by(Property.created_at.desc()).all()

    result = []

    for item in properties:
        property_data = PropertyResponse.model_validate(item)
        property_data.owner_phone = item.owner.phone if item.owner else None

        image_files = []

        if os.path.exists("uploads"):
            for filename in os.listdir("uploads"):
                if filename.startswith(f"property_{item.id}_"):
                    image_files.append(f"/uploads/{filename}")

        property_data.images = image_files
        result.append(property_data)

    return result


# MENING E'LONLARIM
@app.get("/my-properties", response_model=list[PropertyResponse])
def get_my_properties(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    properties = db.query(Property).filter(
        Property.user_id == current_user.id
    ).order_by(Property.created_at.desc()).all()

    return properties


# E'LONNI TAHRIRLASH
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

    return property_item


# E'LONNI O'CHIRISH
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

    return {
        "message": "E'lon muvaffaqiyatli o'chirildi!"
    }


# BITTA E'LONNI RASMLARI BILAN KO'RISH
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

    property_data = PropertyResponse.model_validate(property_item)
    property_data.owner_phone = property_item.owner.phone if property_item.owner else None

    image_files = []

    if os.path.exists("uploads"):
        for filename in os.listdir("uploads"):
            if filename.startswith(f"property_{property_id}_"):
                image_files.append(f"/uploads/{filename}")

    property_data.images = image_files

    return property_data


# E'LONLARNI QIDIRISH VA FILTRLASH
@app.get("/search-properties", response_model=list[PropertyResponse])
def search_properties(
    address: str = None,
    listing_type: str = None,
    min_price: float = None,
    max_price: float = None,
    rooms: int = None,
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

    return query.order_by(
        Property.created_at.desc()
    ).all()


# E'LON RASMINI ALMASHTIRISH
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

    allowed_types = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp"
    }

    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Faqat JPG, PNG yoki WEBP rasm yuklash mumkin"
        )

    os.makedirs("uploads", exist_ok=True)

    # SHU E'LONGA TEGISHLI ESKI RASMLARNI O'CHIRISH
    for old_file in os.listdir("uploads"):
        if old_file.startswith(f"property_{property_id}_"):
            old_path = os.path.join("uploads", old_file)
            if os.path.isfile(old_path):
                os.remove(old_path)

    # YANGI RASMNI SAQLASH
    filename = (
        f"property_{property_id}_{datetime.now().timestamp()}"
        f"{allowed_types[file.content_type]}"
    )

    file_path = os.path.join("uploads", filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "message": "Rasm muvaffaqiyatli almashtirildi",
        "filename": filename,
        "file_path": file_path
    }


# E'LON RASMINI O'CHIRISH
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

    deleted_count = 0

    if os.path.exists("uploads"):
        for filename in os.listdir("uploads"):
            if filename.startswith(f"property_{property_id}_"):
                file_path = os.path.join("uploads", filename)

                if os.path.isfile(file_path):
                    os.remove(file_path)
                    deleted_count += 1

    if deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Bu e'lon uchun rasm topilmadi"
        )

    return {
        "message": "Rasm muvaffaqiyatli o'chirildi",
        "deleted_count": deleted_count
    }


# E'LON UCHUN BIR NECHTA RASM YUKLASH
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

    allowed_types = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp"
    }

    for file in files:
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail="Faqat JPG, PNG yoki WEBP rasmlar mumkin"
            )

    os.makedirs("uploads", exist_ok=True)

    uploaded_files = []

    for index, file in enumerate(files):
        filename = (
            f"property_{property_id}_"
            f"{datetime.now().timestamp()}_{index}"
            f"{allowed_types[file.content_type]}"
        )

        file_path = os.path.join("uploads", filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        uploaded_files.append(filename)

    return {
        "message": "Rasmlar muvaffaqiyatli yuklandi",
        "uploaded_count": len(uploaded_files),
        "files": uploaded_files
    }
    
# E'LON RASMLARINI TO'LIQ ALMASHTIRISH
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

    allowed_types = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp"
    }

    for file in files:
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail="Faqat JPG, PNG yoki WEBP rasmlar mumkin"
            )

    os.makedirs("uploads", exist_ok=True)

    uploaded_files = []

    try:
        for index, file in enumerate(files):
            filename = (
                f"property_{property_id}_"
                f"{datetime.now().timestamp()}_{index}"
                f"{allowed_types[file.content_type]}"
            )

            file_path = os.path.join("uploads", filename)

            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            uploaded_files.append(filename)

        # Yangi rasmlar muvaffaqiyatli saqlangandan keyin eskilarini o'chirish
        for filename in os.listdir("uploads"):
            if filename.startswith(f"property_{property_id}_"):
                old_path = os.path.join("uploads", filename)

                if os.path.isfile(old_path) and filename not in uploaded_files:
                    os.remove(old_path)

    except Exception:
        for filename in uploaded_files:
            path = os.path.join("uploads", filename)
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



# SWAGGER UCHUN RASMLARNI YUKLASH SOZLAMASI
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

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

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi