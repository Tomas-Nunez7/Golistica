from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# URL de conexión a la base de datos, por defecto usa SQLite local
URL_BASE_DATOS = os.getenv('DATABASE_URL', 'sqlite:///./futbol5.db')

# Configurar el motor de la base de datos
# Para SQLite, se desactiva la verificación de hilos múltiples
motor = create_engine(
    URL_BASE_DATOS, 
    connect_args={"check_same_thread": False} if URL_BASE_DATOS.startswith("sqlite") else {}
)

# Crear una fábrica de sesiones para interactuar con la base de datos
SesionLocal = sessionmaker(autocommit=False, autoflush=False, bind=motor)

# Clase base para los modelos de la base de datos
Base = declarative_base()
