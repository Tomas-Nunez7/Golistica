# Futbol5 - Proyecto de Reservas (esqueleto)

Contenido mínimo entregado:
- backend/ : FastAPI app (esqueleto funcional)
- client/ : HTML + JS cliente que usa fetch y async/await
- init_db.sql : script para inicializar la base (SQLite compatible)
- tcp_listener.py : proceso listener TCP para recibir alertas desde el backend
- .env.example : variables de entorno de ejemplo

Instrucciones rápidas:
1. Copiar `.env.example` a `.env` y ajustar si hace falta.
2. Instalar dependencias: `pip install -r requirements.txt`
3. Inicializar BD: `sqlite3 futbol5.db < init_db.sql`  (o usar psql si se migró a Postgres)
4. Opcional: crear usuarios admin/operator usando `sqlite3` o mediante endpoint `/api/users`.
5. Iniciar listener de alertas: `python tcp_listener.py`
6. Iniciar backend: `uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000`
7. Abrir client/index.html en un navegador y usar la UI.

Este paquete es un **esqueleto** pensado para adaptarse y completarse: agregar validaciones, manejar tokens de forma segura, mejorar la UI, y usar PostgreSQL en producción.

Documentación requerida por la consigna (debe completarse por el equipo):
- Política de hashing/cifrado: contraseñas con bcrypt (irreversible). Datos recuperables (tokens externos) cifrados con Fernet/AES (clave en MASTER_KEY).
- Cómo ejecutar las pruebas de concurrencia: abrir 2 navegadores en distintas máquinas apuntando al frontend y ejecutar reserva concurrente para misma cancha/hora (se demostrará que sólo una reserva pasa y la otra recibe 409 Conflict).
