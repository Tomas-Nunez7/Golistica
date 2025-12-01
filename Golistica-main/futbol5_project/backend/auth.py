from datetime import datetime, timedelta
from typing import Optional
import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

from .db import SessionLocal
from . import models, schemas
from .audit import log_action, send_alert

load_dotenv()

# Configuración básica de seguridad (para entorno de práctica)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_IN_ENV")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

MASTER_KEY = os.getenv("MASTER_KEY")
if MASTER_KEY is None:
    MASTER_KEY = Fernet.generate_key().decode()

fernet = Fernet(MASTER_KEY.encode())

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

router = APIRouter(prefix="/api", tags=["auth"])


# Dependencia de BD local a este módulo

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def encrypt_sensitive(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return fernet.encrypt(value.encode()).decode()


def decrypt_sensitive(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        return None


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    # Verificar si el usuario ya existe
    existing = db.query(models.User).filter(models.User.username == payload.username).first()
    if existing:
        log_action(
            db,
            actor_id=None,
            actor_username=None,
            action="register_user_conflict",
            resource_type="user",
            resource_id=payload.username,
            details="Intento de registro con username existente",
            success=False,
        )
        raise HTTPException(status_code=400, detail="El usuario ya existe")

    # Crear usuario nuevo con contraseña hasheada
    user = models.User(
        username=payload.username,
        password_hash=get_password_hash(payload.password),
        email=payload.email,
        role_id=payload.role_id,
        encrypted_data=encrypt_sensitive(payload.email),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_action(
        db,
        actor_id=user.id,
        actor_username=user.username,
        action="register_user",
        resource_type="user",
        resource_id=str(user.id),
        details="Usuario registrado", 
        success=True,
    )

    return {"id": user.id, "username": user.username}


@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        log_action(
            db,
            actor_id=user.id if user else None,
            actor_username=user.username if user else form_data.username,
            action="login_failed",
            resource_type="auth",
            resource_id=None,
            details="Login fallido",
            success=False,
        )
        send_alert(
            db,
            level="warning",
            message="Intento de login fallido",
            payload={"username": form_data.username},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")

    access_token = create_access_token({"sub": str(user.id), "role_id": user.role_id})
    log_action(
        db,
        actor_id=user.id,
        actor_username=user.username,
        action="login_success",
        resource_type="auth",
        resource_id=str(user.id),
        details="Login exitoso",
        success=True,
    )
    return {"access_token": access_token, "token_type": "bearer"}


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar el token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user


@router.get("/me")
def read_me(current_user: models.User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role_id": current_user.role_id,
        "sensitive_data": decrypt_sensitive(current_user.encrypted_data),
    }


def require_user(current_user: models.User = Depends(get_current_user)) -> models.User:
    """Requiere que el usuario esté autenticado (cualquier rol distinto de None)."""
    return current_user


def require_operator_or_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    """Requiere rol operador (2) o admin (3)."""
    if current_user.role_id not in (2, 3):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permisos insuficientes")
    return current_user


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    """Requiere rol admin (3)."""
    if current_user.role_id != 3:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere rol administrador")
    return current_user
