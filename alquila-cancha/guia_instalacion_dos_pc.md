# Guía Detallada: Ejecutar AlquilaCancha en 2 PCs

## PC 1 - Servidor Principal

### Paso 1: Preparar el entorno
```bash
# Navegar al directorio del proyecto
cd "c:/Users/juani/Downloads/Trabajo Alan/alquila-cancha"

# Activar entorno virtual (si existe)
venv\Scripts\activate

# Verificar instalación de dependencias
pip install -r requirements.txt
```

### Paso 2: Configurar el servidor
El archivo `backend/app.py` ya está configurado para aceptar conexiones remotas:
- Host: `0.0.0.0` (permite conexiones desde cualquier IP)
- Puerto: `5002`

### Paso 3: Iniciar el servidor
```bash
# Navegar al directorio backend
cd backend

# Iniciar la aplicación
python app.py
```

### Paso 4: Verificar que el servidor está corriendo
Deberías ver un mensaje similar a:
```
(12345) wsgi starting up on http://0.0.0.0:5002
```

### Paso 5: Obtener la IP del servidor
```bash
# Abrir una nueva terminal y ejecutar
ipconfig
```
Busca la dirección IPv4 (generalmente algo como 192.168.1.XXX)

### Paso 6: Probar acceso local
Abre tu navegador y ve a:
- `http://localhost:5002`
- `http://127.0.0.1:5002`

## PC 2 - Cliente/Segunda Instancia

### Paso 1: Copiar los archivos
Opción A: Copiar toda la carpeta `alquila-cancha` a la segunda PC
Opción B: Clonar el repositorio si está disponible

### Paso 2: Instalar Python y dependencias
```bash
# Asegurarse de tener Python 3.8+ instalado
python --version

# Navegar al directorio del proyecto
cd "ruta/donde/copiaste/alquila-cancha"

# Crear entorno virtual (recomendado)
python -m venv venv
venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```

### Paso 3: Configurar para acceso remoto

#### Opción A: Conectar al servidor principal
1. Modificar el archivo `.env` para que apunte al servidor:
```env
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=your-secret-key-here
# Apuntar a la base de datos del servidor (si comparten red)
SQLALCHEMY_DATABASE_URI=sqlite:///\\\\\\SERVIDOR\\ruta\\compartida\\alquila_cancha.db
```

#### Opción B: Ejecutar instancia independiente
Mantener la configuración actual:
```env
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=your-secret-key-here
SQLALCHEMY_DATABASE_URI=sqlite:///alquila_cancha.db
```

### Paso 4: Iniciar la aplicación en PC 2
```bash
cd backend
python app.py
```

### Paso 5: Acceder desde PC 2 al servidor principal
Abre el navegador en PC 2 y ve a:
- `http://[IP_DEL_SERVIDOR]:5002`
  (reemplaza [IP_DEL_SERVIDOR] con la IP obtenida en el Paso 5 del PC 1)

## Opción de Base de Datos Compartida

### Si quieres que ambas PCs compartan los mismos datos:

#### Método 1: Carpeta compartida en red
1. En PC 1, comparte la carpeta que contiene `alquila_cancha.db`
2. En PC 2, modifica el `.env`:
```env
SQLALCHEMY_DATABASE_URI=sqlite:///\\\\\\PC1_NOMBRE\\carpeta_compartida\\alquila_cancha.db
```

#### Método 2: Base de datos centralizada (recomendado)
1. Instalar PostgreSQL o MySQL en PC 1
2. Crear base de datos y usuario
3. Modificar `.env` en ambas PCs:
```env
# Para PostgreSQL
SQLALCHEMY_DATABASE_URI=postgresql://usuario:password@IP_DEL_SERVIDOR:5432/nombre_db

# Para MySQL
SQLALCHEMY_DATABASE_URI=mysql://usuario:password@IP_DEL_SERVIDOR:3306/nombre_db
```

## Verificación de Conectividad

### Paso 1: Probar conexión de red
Desde PC 2, ejecutar en terminal:
```bash
ping [IP_DEL_SERVIDOR]
```

### Paso 2: Probar puerto específico
```bash
telnet [IP_DEL_SERVIDOR] 5002
```

### Paso 3: Verificar firewall
Asegúrate de que el firewall en PC 1 permita conexiones entrantes al puerto 5002.

## Solución de Problemas Comunes

### Problema: "Connection refused"
**Causa:** Firewall bloqueando el puerto o servidor no iniciado
**Solución:**
1. Verifica que el servidor está corriendo en PC 1
2. Configura firewall para permitir puerto 5002

### Problema: Base de datos no encontrada
**Causa:** Ruta incorrecta en `.env`
**Solución:** Verifica que la ruta a la base de datos sea correcta

### Problema: Error de permisos
**Causa:** La carpeta compartida no tiene permisos de escritura
**Solución:** Configura permisos apropiados en la carpeta compartida

## Resumen de URLs de Acceso

- **PC 1 (local):** `http://localhost:5002`
- **PC 1 (desde otra PC):** `http://[IP_PC1]:5002`
- **PC 2 (local):** `http://localhost:5002`
- **PC 2 (desde otra PC):** `http://[IP_PC2]:5002`

## Notas Finales

1. Cada PC ejecutará su propia instancia si no configuras base de datos compartida
2. Para desarrollo y pruebas, las instancias separadas son suficientes
3. Para producción, considera usar una base de datos centralizada
4. SocketIO permite comunicación en tiempo real dentro de cada instancia
