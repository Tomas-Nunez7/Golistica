import os
import sqlite3
from config import app, db
from models import create_admin_user, add_sample_courts

def reset_database():
    """Elimina y recrea la base de datos"""
    db_path = 'instance/alquila_cancha.db'
    
    # Cerrar conexión si existe
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print("Base de datos eliminada")
        except Exception as e:
            print(f"Error eliminando base de datos: {e}")
            return False
    
    # Crear nueva base de datos
    with app.app_context():
        db.create_all()
        create_admin_user()
        add_sample_courts()
        print("Nueva base de datos creada con todos los campos")
    
    return True

if __name__ == '__main__':
    reset_database()
