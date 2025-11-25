from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel
import bcrypt
from sqlalchemy.orm import Session

# Importar la configuración de la base de datos
from database import engine, SessionLocal, Rol, Usuario, Cancha, crear_tablas

# Crear las tablas en la base de datos
crear_tablas()

app = FastAPI()

# Configuración
SECRET_KEY = "tu_clave_secreta_aqui"  # Cambia esto en producción
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Modelo de usuario
class User(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None

class UserInDB(User):
    hashed_password: str

# Configurar archivos estáticos
app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).parent / "static")),
    name="static"
)

# Configurar plantillas
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Dependencia para obtener la sesión de la base de datos
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Funciones de utilidad
def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_user(db: Session, username: str):
    return db.query(Usuario).filter(Usuario.nombre_usuario == username).first()

def authenticate_user(db: Session, username: str, password: str):
    user = get_user(db, username)
    if not user:
        return False
    if not verify_password(password, user.contrasena_hash):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Middleware para verificar el token JWT
async def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("token")
    if not token:
        return None
    
    try:
        token = token.replace("Bearer ", "")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None
    
    user = get_user(db, username)
    if user is None:
        return None
    
    return user

# Rutas
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    canchas = db.query(Cancha).filter(Cancha.activa == True).all()
    return templates.TemplateResponse("index.html", {"request": request, "user": user, "canchas": canchas})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = authenticate_user(db, username, password)
    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Datos incorrectos"})
    
    # Actualizar último acceso
    user.ultimo_acceso = datetime.utcnow()
    db.commit()
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.nombre_usuario}, expires_delta=access_token_expires)
    
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="token", value=f"Bearer {access_token}", httponly=True, max_age=1800)
    return response

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("registro.html", {"request": request})

@app.post("/register")
async def register(request: Request, username: str = Form(...), password: str = Form(...), email: str = Form(None), db: Session = Depends(get_db)):
    # Verificar si el usuario ya existe
    db_user = get_user(db, username)
    if db_user:
        return templates.TemplateResponse("registro.html", {"request": request, "error": "Usuario existente"})
    
    # Obtener el rol de usuario por defecto
    rol = db.query(Rol).filter(Rol.nombre == "usuario").first()
    if not rol:
        # Si no existe el rol, crearlo
        rol = Rol(nombre="usuario")
        db.add(rol)
        db.commit()
        db.refresh(rol)
    
    # Crear el nuevo usuario
    hashed_password = get_password_hash(password)
    db_user = Usuario(
        nombre_usuario=username,
        email=email,
        contrasena_hash=hashed_password,
        rol_id=rol.id,
        activo=True
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie(key="token")
    return response

@app.get("/cancha/{cancha_id}", response_class=HTMLResponse)
async def ver_cancha(request: Request, cancha_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cancha = db.query(Cancha).filter(Cancha.id == cancha_id).first()
    if not cancha:
        return RedirectResponse(url="/")
    
    return templates.TemplateResponse("cancha_detalle.html", {"request": request, "cancha": cancha, "user": user})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)