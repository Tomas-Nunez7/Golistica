from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from . import db, models, utils, schemas
from .db import SessionLocal, motor, Base
from sqlalchemy.exc import IntegrityError
import uvicorn
from jose import jwt
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de seguridad
CLAVE_SECRETA = os.getenv('APP_SECRET_KEY', 'cambiar-esta-clave')
ALGORITMO = 'HS256'

# Crear tablas en la base de datos
Base.metadata.create_all(bind=motor)

# Inicializar la aplicación FastAPI
app = FastAPI(title='Futbol5 - API de Reservas')

def obtener_sesion():
    """Crea y maneja una sesión de base de datos"""
    sesion = SesionLocal()
    try:
        yield sesion
    finally:
        sesion.close()

def registrar_accion(sesion: Session, actor, accion, tipo_recurso=None, id_recurso=None, detalles=None, exito=True):
    """Registra una acción en el log de auditoría"""
    try:
        registro = models.RegistroAuditoria(
            id_actor=actor.id if actor else None,
            nombre_usuario=actor.username if actor else None,
            accion=accion, 
            tipo_recurso=tipo_recurso,
            id_recurso=str(id_recurso) if id_recurso else None,
            detalles=detalles and str(detalles),
            exito=1 if exito else 0
        )
        sesion.add(registro)
        sesion.commit()
    except Exception as e:
        sesion.rollback()
        print('Error al escribir en el registro de auditoría:', e)

@app.post('/api/auth/login')
def iniciar_sesion(credenciales: schemas.LoginIn, sesion: Session = Depends(obtener_sesion)):
    """Endpoint para iniciar sesión"""
    usuario = sesion.query(models.Usuario).filter(models.Usuario.username == credenciales.username).first()
    
    if not usuario or not utils.verificar_contrasena(credenciales.password, usuario.contrasena_hash):
        # Registrar intento fallido
        registrar_accion(sesion, None, 'inicio_sesion_fallido', 
                        tipo_recurso='usuario', 
                        id_recurso=credenciales.username, 
                        detalles='credenciales inválidas', 
                        exito=False)
        
        # Crear alerta de seguridad
        alerta = models.Alerta(
            nivel='CRITICO', 
            mensaje='Intento de inicio de sesión fallido', 
            datos_adicionales=str({'username': credenciales.username}))
        
        sesion.add(alerta)
        sesion.commit()
        utils.enviar_alerta_tcp({
            'nivel': 'CRITICO',
            'mensaje': 'Inicio de sesión fallido',
            'usuario': credenciales.username
        })
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail='Credenciales inválidas')
    
    # Actualizar último inicio de sesión
    from datetime import datetime
    usuario.ultimo_inicio_sesion = datetime.utcnow()
    sesion.add(usuario)
    sesion.commit()
    
    registrar_accion(sesion, usuario, 'inicio_sesion_exitoso', 
                    tipo_recurso='usuario', 
                    id_recurso=usuario.id, 
                    detalles='inicio de sesión exitoso', 
                    exito=True)
    
    # Generar token JWT
    token = jwt.encode(
        {'sub': usuario.username, 'rol': usuario.rol.nombre}, 
        CLAVE_SECRETA, 
        algorithm=ALGORITMO
    )
    
    return {'token_acceso': token, 'rol': usuario.rol.nombre}

from typing import Optional
from pydantic import BaseModel

def obtener_usuario_actual(token: str = Depends(lambda: None), sesion: Session = Depends(obtener_sesion)):
    """
    Obtiene el usuario actual a partir del token JWT.
    En producción, se recomienda usar una dependencia que lea correctamente el encabezado de autorización.
    """
    from fastapi import Request
    
    def _dependencia(request: Request):
        # Obtener el token del encabezado de autorización
        autorizacion = request.headers.get('authorization')
        if not autorizacion or not autorizacion.lower().startswith('bearer '):
            raise HTTPException(status_code=401, detail='Token no proporcionado')
        
        token = autorizacion.split(' ', 1)[1]
        
        try:
            # Decodificar el token JWT
            payload = jwt.decode(token, CLAVE_SECRETA, algorithms=[ALGORITMO])
            nombre_usuario = payload.get('sub')
            
            # Buscar el usuario en la base de datos
            usuario = sesion.query(models.Usuario).filter(
                models.Usuario.username == nombre_usuario
            ).first()
            
            if not usuario:
                raise HTTPException(status_code=401, detail='Token inválido')
                
            return usuario
            
        except Exception as e:
            print(f"Error al decodificar el token: {e}")
            raise HTTPException(status_code=401, detail='Token inválido')
            
    return _dependencia

@app.post('/api/users', status_code=201)
def crear_usuario(datos: schemas.UsuarioCrear, sesion: Session = Depends(obtener_sesion)):
    """
    Crea un nuevo usuario en el sistema.
    """
    # Hashear la contraseña antes de guardarla
    contrasena_hasheada = utils.hashear_contrasena(datos.password)
    
    try:
        # Crear el nuevo usuario
        nuevo_usuario = models.Usuario(
            username=datos.username,
            contrasena_hash=contrasena_hasheada,
            email=datos.email,
            rol_id=datos.rol_id
        )
        
        # Guardar en la base de datos
        sesion.add(nuevo_usuario)
        sesion.commit()
        
        # Registrar la acción en el log de auditoría
        registrar_accion(
            sesion=sesion,
            actor=nuevo_usuario,
            accion='usuario_creado',
            tipo_recurso='usuario',
            id_recurso=nuevo_usuario.id,
            detalles='Nuevo usuario creado exitosamente',
            exito=True
        )
        
        return {
            'id': nuevo_usuario.id, 
            'username': nuevo_usuario.username
        }
        
    except IntegrityError:
        # En caso de violación de unicidad (usuario ya existe)
        sesion.rollback()
        raise HTTPException(
            status_code=400, 
            detail='El nombre de usuario ya está en uso'
        )

@app.get('/api/courts')
def listar_canchas(sesion: Session = Depends(obtener_sesion)):
    """
    Obtiene la lista de todas las canchas disponibles.
    """
    canchas = sesion.query(models.Cancha).all()
    return [
        {
            'id': cancha.id,
            'nombre': cancha.nombre,
            'ubicacion': cancha.ubicacion,
            'precio': str(cancha.precio)
        } 
        for cancha in canchas
    ]

@app.post('/api/courts', status_code=201)
def crear_cancha(
    datos: schemas.CanchaEntrada, 
    usuario=Depends(obtener_usuario_actual()), 
    sesion: Session = Depends(obtener_sesion)
):
    """
    Crea una nueva cancha en el sistema.
    Requiere privilegios de operador o administrador.
    """
    # Verificar permisos del usuario
    if usuario.rol.nombre not in ('operador', 'admin'):
        registrar_accion(
            sesion=sesion,
            actor=usuario,
            accion='intento_creacion_cancha_no_autorizado',
            tipo_recurso='cancha',
            detalles='Usuario sin permisos para crear canchas',
            exito=False
        )
        raise HTTPException(
            status_code=403, 
            detail='No tiene permisos para realizar esta acción'
        )
    
    # Crear la nueva cancha
    nueva_cancha = models.Cancha(
        nombre=datos.nombre,
        ubicacion=datos.ubicacion,
        precio=datos.precio
    )
    
    # Guardar en la base de datos
    sesion.add(nueva_cancha)
    sesion.commit()
    
    # Registrar la acción exitosa
    registrar_accion(
        sesion=sesion,
        actor=usuario,
        accion='cancha_creada',
        tipo_recurso='cancha',
        id_recurso=nueva_cancha.id,
        detalles=f'Cancha {nueva_cancha.nombre} creada exitosamente',
        exito=True
    )
    
    return {'id': nueva_cancha.id}

@app.post('/api/reservations', status_code=201)
def crear_reserva(
    datos: schemas.ReservaEntrada, 
    usuario=Depends(obtener_usuario_actual()), 
    sesion: Session = Depends(obtener_sesion)
):
    """
    Crea una nueva reserva de cancha.
    Verifica que no haya conflictos de horario antes de crear la reserva.
    """
    # Verificar si hay reservas que se superponen
    reserva_superpuesta = sesion.query(models.Reserva).filter(
        models.Reserva.id_cancha == datos.id_cancha,
        models.Reserva.estado == 'activa',
        models.Reserva.fecha_hora_inicio < datos.fecha_hora_fin,
        models.Reserva.fecha_hora_fin > datos.fecha_hora_inicio
    ).first()
    
    if reserva_superpuesta:
        # Registrar el conflicto
        registrar_accion(
            sesion=sesion,
            actor=usuario,
            accion='conflicto_reserva',
            tipo_recurso='reserva',
            detalles=f'Intento de reserva en horario ocupado. ID de reserva conflictiva: {reserva_superpuesta.id}',
            exito=False
        )
        
        # Crear alerta
        alerta = models.Alerta(
            nivel='ADVERTENCIA',
            mensaje='Conflicto de reserva detectado',
            datos_adicionales=str({
                'usuario': usuario.username,
                'cancha': datos.id_cancha,
                'intento_fecha_hora_inicio': str(datos.fecha_hora_inicio),
                'intento_fecha_hora_fin': str(datos.fecha_hora_fin)
            })
        )
        
        sesion.add(alerta)
        sesion.commit()
        
        # Enviar alerta por TCP (si está configurado)
        utils.enviar_alerta_tcp({
            'nivel': 'ADVERTENCIA',
            'mensaje': 'Conflicto de reserva',
            'usuario': usuario.username,
            'cancha': datos.id_cancha
        })
        
        raise HTTPException(
            status_code=409,
            detail='El horario seleccionado ya está reservado'
        )
    
    # Crear la nueva reserva
    nueva_reserva = models.Reserva(
        id_cancha=datos.id_cancha,
        id_usuario=usuario.id,
        fecha_hora_inicio=datos.fecha_hora_inicio,
        fecha_hora_fin=datos.fecha_hora_fin,
        estado='activa'
    )
    
    sesion.add(nueva_reserva)
    
    # Actualizar estadísticas del usuario
    estadisticas_usuario = sesion.query(models.EstadisticasReservasUsuario).filter(
        models.EstadisticasReservasUsuario.id_usuario == usuario.id
    ).first()
    
    if not estadisticas_usuario:
        estadisticas_usuario = models.EstadisticasReservasUsuario(
            id_usuario=usuario.id,
            total_reservas=1
        )
        sesion.add(estadisticas_usuario)
    else:
        estadisticas_usuario.total_reservas += 1
    
    # Confirmar todos los cambios en la base de datos
    sesion.commit()
    
    # Registrar la acción exitosa
    registrar_accion(
        sesion=sesion,
        actor=usuario,
        accion='reserva_creada',
        tipo_recurso='reserva',
        id_recurso=nueva_reserva.id,
        detalles=f'Reserva creada exitosamente para la cancha {datos.id_cancha}',
        exito=True
    )
    
    return {'id': nueva_reserva.id}

@app.get('/api/audit_log')
def obtener_registro_auditoria(
    sesion: Session = Depends(obtener_sesion),
    usuario=Depends(obtener_usuario_actual())
):
    """
    Obtiene el registro de auditoría del sistema.
    Requiere privilegios de administrador.
    """
    # Verificar permisos de administrador
    if usuario.rol.nombre != 'admin':
        raise HTTPException(
            status_code=403,
            detail='Se requieren privilegios de administrador para acceder a estos registros'
        )
    
    # Obtener los últimos 200 registros de auditoría
    registros = sesion.query(models.RegistroAuditoria)\
        .order_by(models.RegistroAuditoria.fecha_creacion.desc())\
        .limit(200)\
        .all()
    
    # Formatear la respuesta
    return [
        {
            'id': registro.id,
            'actor': registro.nombre_usuario,
            'accion': registro.accion,
            'detalles': registro.detalles,
            'fecha_creacion': str(registro.fecha_creacion),
            'tipo_recurso': registro.tipo_recurso,
            'id_recurso': registro.id_recurso,
            'exito': bool(registro.exito)
        }
        for registro in registros
    ]

if __name__ == '__main__':
    """
    Punto de entrada principal de la aplicación.
    Inicia el servidor Uvicorn con la configuración especificada.
    """
    uvicorn.run(
        'backend.main:app',
        host='0.0.0.0',
        port=8000,
        reload=True  # Recarga automática en desarrollo
    )
