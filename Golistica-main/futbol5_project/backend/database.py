from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session as DBSession
from datetime import datetime
from typing import Optional
import os

# URL de la base de datos SQLite
DATABASE_URL = "sqlite:///./golistica.db"

# Crear motor de base de datos
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

# Sesión local
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Clase base para los modelos
Base = declarative_base()

# Dependencia para obtener la sesión de la base de datos
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Modelos
class Rol(Base):
    __tablename__ = "roles"
    
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, unique=True, nullable=False)
    
    usuarios = relationship("Usuario", back_populates="rol")

class Usuario(Base):
    __tablename__ = "usuarios"
    
    id = Column(Integer, primary_key=True, index=True)
    nombre_usuario = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    contrasena_hash = Column(String, nullable=False)
    rol_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    ultimo_acceso = Column(DateTime, nullable=True)
    activo = Column(Boolean, default=True)
    
    rol = relationship("Rol", back_populates="usuarios")

class Cancha(Base):
    __tablename__ = "canchas"
    
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    descripcion = Column(String, nullable=True)
    superficie = Column(String, nullable=True)
    horario = Column(String, nullable=True)
    ubicacion = Column(String, nullable=True)
    imagen = Column(String, nullable=True)
    activa = Column(Boolean, default=True)

# Crear tablas en la base de datos
def crear_tablas():
    Base.metadata.create_all(bind=engine)
    
    # Crear roles por defecto si no existen
    db = SessionLocal()
    try:
        # Verificar si el rol de administrador existe
        admin_rol = db.query(Rol).filter(Rol.nombre == "admin").first()
        if not admin_rol:
            admin_rol = Rol(nombre="admin")
            db.add(admin_rol)
        
        # Verificar si el rol de usuario existe
        usuario_rol = db.query(Rol).filter(Rol.nombre == "usuario").first()
        if not usuario_rol:
            usuario_rol = Rol(nombre="usuario")
            db.add(usuario_rol)
        
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
