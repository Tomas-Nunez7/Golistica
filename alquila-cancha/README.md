# AlquilaCancha - Plataforma de Reserva de Canchas Deportivas

Una plataforma web para buscar, reservar y gestionar canchas deportivas. Este proyecto está desarrollado con Python (Flask) para el backend, SQLite para la base de datos, y HTML, CSS y JavaScript para el frontend.

## Características

- Búsqueda de canchas por ubicación, tipo y disponibilidad
- Sistema de reservas en línea
- Perfiles de canchas con fotos y detalles
- Panel de administración para gestores de canchas
- Diseño responsive para móviles y escritorio

## Requisitos Previos

- Python 3.8 o superior
- pip (gestor de paquetes de Python)
- Navegador web moderno (Chrome, Firefox, Safari, Edge)

## Instalación

1. Clona el repositorio o descarga los archivos

2. Crea un entorno virtual (recomendado):
   ```
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```

3. Instala las dependencias:
   ```
   pip install -r requirements.txt
   ```

## Configuración

1. Crea un archivo `.env` en la raíz del proyecto con las siguientes variables:
   ```
   FLASK_APP=app.py
   FLASK_ENV=development
   SECRET_KEY=tu_clave_secreta_aqui
   ```

## Ejecución

1. Inicia la aplicación:
   ```
   flask run
   ```

2. Abre tu navegador y ve a:
   ```
   http://127.0.0.1:5000/
   ```

## Estructura del Proyecto

```
alquila-cancha/
├── static/
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   └── main.js
│   └── images/
├── templates/
│   └── index.html
├── database/
│   └── alquila_cancha.db
├── app.py
├── requirements.txt
└── README.md
```

## Uso

1. **Usuarios**:
   - Busca canchas por ubicación, tipo o disponibilidad
   - Selecciona una cancha para ver más detalles
   - Haz clic en "Reservar" para seleccionar fecha y hora
   - Completa el formulario de reserva

2. **Administradores**:
   - Accede al panel de administración en `/admin` (a implementar)
   - Gestiona canchas, reservas y usuarios

## Tecnologías Utilizadas

- **Backend**: Python, Flask, SQLAlchemy
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **Base de datos**: SQLite
- **Diseño**: CSS Grid, Flexbox, Responsive Design

## Contribución

Las contribuciones son bienvenidas. Por favor, abre un issue primero para discutir los cambios que te gustaría hacer.

## Licencia

Este proyecto está bajo la Licencia MIT. Ver el archivo `LICENSE` para más detalles.
