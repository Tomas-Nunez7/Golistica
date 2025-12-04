from flask import request, session, jsonify
from flask_socketio import emit, join_room
from datetime import datetime
import json
import multiprocessing
import time
import uuid
import random
from config import app, socketio
from models import User, log_audit, Payment, Booking
# Variables globales para gestores (se inicializarán en app.py)
process_manager = None
thread_pool = None
resource_monitor = None

def get_thread_pool():
    """Obtiene el thread pool global"""
    global thread_pool
    return thread_pool

def get_process_manager():
    """Obtiene el process manager global"""
    global process_manager
    return process_manager

def get_resource_monitor():
    """Obtiene el resource monitor global"""
    global resource_monitor
    return resource_monitor
from routes import admin_required, login_required

# Eventos de SocketIO
@socketio.on('connect')
def handle_connect():
    print(f'Cliente conectado: {request.sid}')
    
    # Si es administrador, unir a la sala de admin
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user and user.is_admin():
            socketio.emit('admin_connected', {'message': 'Administrador conectado'}, room=request.sid)

@socketio.on('join_admin_room')
def handle_join_admin_room():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user and user.is_admin():
            socketio.join_room('admin_room')
            emit('joined_admin_room', {'message': 'Te uniste a la sala de administradores'})

@socketio.on('join_user_room')
def handle_join_user_room(data):
    """Une al usuario a su sala personal para notificaciones"""
    if 'user_id' in session:
        user_id = data.get('user_id') or session['user_id']
        socketio.join_room(f'user_{user_id}')
        emit('joined_user_room', {'message': f'Te uniste a tu sala personal'})

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Cliente desconectado: {request.sid}')

@socketio.on('send_notification')
def handle_notification(data):
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user and user.is_admin():
            socketio.emit('notification', {
                'message': data['message'],
                'type': data.get('type', 'info'),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }, room='admin_room')

@socketio.on('court_added_notification')
def handle_court_added(data):
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user and user.is_operator():
            socketio.emit('court_added', {
                'court_id': data['court_id'],
                'court_name': data['court_name'],
                'added_by': session.get('username', 'Unknown')
            }, room='admin_room')

# Endpoints para gestión de procesos y tareas
@app.route('/api/tasks/start', methods=['POST'])
@admin_required
def start_background_task():
    """Inicia una tarea en segundo plano"""
    data = request.get_json()
    task_type = data.get('task_type')
    
    if not task_type:
        return jsonify({'success': False, 'message': 'Task type required'}), 400
    
    task_id = f"{task_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    
    # Seleccionar la función de tarea apropiada
    from config import data_integrity_check_task, statistics_calculation_task
    task_functions = {
        'data_integrity': data_integrity_check_task,
        'statistics': statistics_calculation_task
    }
    
    if task_type not in task_functions:
        return jsonify({'success': False, 'message': 'Invalid task type'}), 400
    
    success, message = process_manager.start_background_task(
        task_functions[task_type], 
        task_id
    )
    
    if success:
        log_audit(
            'start_background_task',
            resource_type='task',
            details=f'Iniciada tarea {task_type} con ID {task_id}'
        )
        return jsonify({
            'success': True, 
            'message': message,
            'task_id': task_id
        })
    else:
        return jsonify({'success': False, 'message': message}), 400

@app.route('/api/tasks/<task_id>/status', methods=['GET'])
@admin_required
def get_task_status(task_id):
    """Obtiene el estado de una tarea"""
    task_status = process_manager.get_task_status(task_id)
    
    if task_status is None:
        return jsonify({'success': False, 'message': 'Task not found'}), 404
    
    return jsonify({
        'success': True,
        'task_status': task_status
    })

@app.route('/api/tasks', methods=['GET'])
@admin_required
def list_all_tasks():
    """Lista todas las tareas activas"""
    process_tasks = process_manager.processes
    thread_tasks = thread_pool.get_all_active_tasks()
    
    return jsonify({
        'success': True,
        'process_tasks': process_tasks,
        'thread_tasks': thread_tasks,
        'total_processes': len(process_tasks),
        'total_threads': len(thread_tasks)
    })

@app.route('/api/tasks/<task_id>/cancel', methods=['DELETE'])
@admin_required
def cancel_task(task_id):
    """Cancela una tarea"""
    success = process_manager.cancel_task(task_id)
    
    if success:
        log_audit(
            'cancel_background_task',
            resource_type='task',
            details=f'Cancelada tarea con ID {task_id}'
        )
        return jsonify({'success': True, 'message': 'Task cancelled'})
    else:
        return jsonify({'success': False, 'message': 'Task not found or cannot be cancelled'}), 404

@app.route('/api/tasks/cleanup', methods=['POST'])
@admin_required
def cleanup_tasks():
    """Limpia tareas completadas"""
    process_manager.cleanup_completed_tasks()
    thread_pool.cleanup_completed_tasks()
    
    log_audit(
        'cleanup_tasks',
        details='Limpieza de tareas completadas'
    )
    
    return jsonify({'success': True, 'message': 'Tasks cleaned up'})

# Endpoint para monitoreo de recursos
@app.route('/api/system/stats', methods=['GET'])
@admin_required
def get_system_stats():
    """Obtiene estadísticas del sistema"""
    stats = resource_monitor.get_stats()
    
    # Agregar información de tareas
    stats.update({
        'active_process_tasks': len(process_manager.processes),
        'active_thread_tasks': len(thread_pool.active_tasks),
        'cpu_count': multiprocessing.cpu_count(),
        'max_thread_workers': thread_pool.executor._max_workers
    })
    
    return jsonify({
        'success': True,
        'stats': stats
    })

# Endpoint para iniciar/detener monitoreo
@app.route('/api/system/monitoring', methods=['POST'])
@admin_required
def toggle_monitoring():
    """Inicia o detiene el monitoreo de recursos"""
    data = request.get_json()
    action = data.get('action')  # 'start' o 'stop'
    
    if action == 'start':
        resource_monitor.start_monitoring()
        log_audit('start_monitoring', details='Iniciado monitoreo de recursos')
        return jsonify({'success': True, 'message': 'Monitoring started'})
    elif action == 'stop':
        resource_monitor.stop_monitoring()
        log_audit('stop_monitoring', details='Detenido monitoreo de recursos')
        return jsonify({'success': True, 'message': 'Monitoring stopped'})
    else:
        return jsonify({'success': False, 'message': 'Invalid action'}), 400

# Endpoint para ejecutar tareas en pool de hilos
@app.route('/api/tasks/thread', methods=['POST'])
@admin_required
def submit_thread_task():
    """Envía una tarea al pool de hilos"""
    data = request.get_json()
    task_type = data.get('task_type')
    
    if not task_type:
        return jsonify({'success': False, 'message': 'Task type required'}), 400
    
    # Definir tareas que pueden ejecutarse en hilos
    def send_notification_task(message, user_type='all'):
        """Tarea para enviar notificaciones"""
        try:
            socketio.emit('notification', {
                'message': message,
                'type': 'info',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }, room='admin_room' if user_type == 'admin' else None)
            return {'success': True, 'message': 'Notification sent'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def log_cleanup_task():
        """Tarea para limpiar logs antiguos"""
        try:
            # Simular limpieza de logs
            time.sleep(0.5)
            return {'success': True, 'cleaned_logs': 10}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    thread_tasks = {
        'notification': send_notification_task,
        'log_cleanup': log_cleanup_task
    }
    
    if task_type not in thread_tasks:
        return jsonify({'success': False, 'message': 'Invalid task type'}), 400
    
    # Obtener argumentos para la tarea
    args = data.get('args', [])
    
    task_id, message = thread_pool.submit_task(thread_tasks[task_type], *args)
    
    if task_id:
        log_audit(
            'submit_thread_task',
            resource_type='task',
            details=f'Enviada tarea {task_type} a pool de hilos con ID {task_id}'
        )
        return jsonify({
            'success': True,
            'message': message,
            'task_id': task_id
        })
    else:
        return jsonify({'success': False, 'message': message}), 400

@app.route('/api/tasks/thread/<task_id>/result', methods=['GET'])
@admin_required
def get_thread_task_result(task_id):
    """Obtiene el resultado de una tarea de hilo"""
    result, message = thread_pool.get_task_result(task_id)
    
    if result is not None and message != "Task not found":
        return jsonify({
            'success': True,
            'result': result,
            'message': message
        })
    else:
        return jsonify({'success': False, 'message': message}), 404

# Sistema de procesamiento de pagos con hilos
def process_deposit_payment(payment_id, booking_id, user_id, amount, payment_method):
    """Procesa el pago de la seña en un hilo separado"""
    print(f"DEBUG - Iniciando procesamiento de pago en hilo: payment_id={payment_id}, booking_id={booking_id}")
    
    # Crear nueva sesión para este hilo
    from config import app, db
    with app.app_context():
        try:
            # Simular procesamiento de pago (en producción sería integración con pasarela de pago)
            processing_time = random.uniform(1, 3)  # 1-3 segundos de procesamiento
            print(f"DEBUG - Simulando procesamiento por {processing_time:.1f} segundos")
            time.sleep(processing_time)
            print(f"DEBUG - Procesamiento completado, verificando aprobación")
            
            # Simular aprobación/rechazo (90% aprobación)
            approved = random.random() < 0.9
            
            payment = Payment.query.get(payment_id)
            
            if approved:
                # Actualizar pago como completado
                payment.status = 'completed'
                payment.transaction_id = f"TXN_{uuid.uuid4().hex[:8].upper()}"
                payment.processed_at = datetime.now()
                
                # Actualizar reserva
                booking = Booking.query.get(booking_id)
                booking.payment_status = 'paid'
                
                print(f"DEBUG - Pago aprobado: {payment.transaction_id}")
                
                # Enviar notificación via SocketIO
                socketio.emit('payment_successful', {
                    'payment_id': payment_id,
                    'booking_id': booking_id,
                    'status': payment.status,
                    'transaction_id': payment.transaction_id,
                    'message': 'Seña procesada correctamente'
                }, room=f"user_{user_id}")
                
                return {
                    'success': True,
                    'payment_id': payment_id,
                    'status': payment.status,
                    'transaction_id': payment.transaction_id
                }
                
            else:
                # Actualizar pago como fallido
                payment.status = 'failed'
                payment.error_message = 'Tarjeta rechazada por el banco emisor'
                payment.processed_at = datetime.now()
                
                # Cancelar reserva
                booking = Booking.query.get(booking_id)
                booking.status = 'cancelled'
                booking.payment_status = 'failed'
                
                print(f"DEBUG - Pago rechazado")
                
                # Enviar notificación via SocketIO
                socketio.emit('payment_failed', {
                    'payment_id': payment_id,
                    'booking_id': booking_id,
                    'amount': amount,
                    'error': payment.error_message,
                    'message': 'Pago rechazado'
                }, room=f"user_{user_id}")
                
                return {
                    'success': False,
                    'payment_id': payment_id,
                    'error': payment.error_message,
                    'booking_status': 'cancelled',
                    'message': 'Pago rechazado'
                }
            
        except Exception as e:
            print(f"DEBUG - Error en procesamiento de pago: {e}")
            
            # Actualizar pago como fallido
            payment = Payment.query.get(payment_id)
            if payment:
                payment.status = 'failed'
                payment.error_message = str(e)
                payment.processed_at = datetime.utcnow()
            
            # Cancelar reserva
            booking = Booking.query.get(booking_id)
            if booking:
                booking.status = 'cancelled'
                booking.payment_status = 'failed'
            
            # Enviar notificación de error
            socketio.emit('payment_error', {
                'payment_id': payment_id,
                'booking_id': booking_id,
                'error': str(e),
                'message': 'Error en el procesamiento del pago'
            }, room=f"user_{user_id}")
            
            return {
                'success': False,
                'payment_id': payment_id,
                'error': str(e),
                'message': 'Error en el procesamiento del pago'
            }

@app.route('/api/payments/deposit', methods=['POST'])
@login_required
def create_deposit_payment():
    """Crea y procesa un pago de seña"""
    print("DEBUG - Iniciando proceso de pago de seña")
    
    try:
        data = request.get_json()
        print(f"DEBUG - Datos recibidos: {data}")
        
        booking_id = data.get('booking_id')
        payment_method = data.get('payment_method', 'credit_card')
        
        print(f"DEBUG - booking_id: {booking_id}, payment_method: {payment_method}")
        print(f"DEBUG - user_id en sesión: {session.get('user_id')}")
        
        # Obtener reserva
        booking = Booking.query.get(booking_id)
        print(f"DEBUG - Reserva encontrada: {booking}")
        
        if not booking:
            print("DEBUG - Reserva no encontrada")
            return jsonify({
                'success': False,
                'message': 'Reserva no encontrada'
            }), 404
        
        # Verificar que el usuario sea el dueño de la reserva
        if booking.user_id != session['user_id']:
            return jsonify({
                'success': False,
                'message': 'No autorizado para procesar este pago'
            }), 403
        
        # Verificar que no tenga pagos previos
        existing_payment = Payment.query.filter_by(
            booking_id=booking_id,
            payment_type='deposit',
            status='completed'
        ).first()
        
        if existing_payment:
            return jsonify({
                'success': False,
                'message': 'Esta reserva ya tiene un pago de seña procesado'
            }), 400
        
        # Crear registro de pago
        payment = Payment(
            booking_id=booking_id,
            user_id=session['user_id'],
            amount=booking.deposit_amount,
            payment_type='deposit',
            payment_method=payment_method,
            status='pending'
        )
        
        from config import db
        db.session.add(payment)
        db.session.commit()
        
        # Unir usuario a sala de SocketIO para notificaciones
        socketio.emit('join_payment_room', {'user_id': session['user_id']})
        
        # Procesar pago directamente (sincrónico temporalmente)
        print(f"DEBUG - Procesando pago sincrónicamente")
        
        try:
            # Simular procesamiento directamente aquí (sin llamar a otra función)
            processing_time = random.uniform(1, 3)
            print(f"DEBUG - Simulando procesamiento por {processing_time:.1f} segundos")
            time.sleep(processing_time)
            
            # Simular aprobación/rechazo (90% aprobación)
            approved = random.random() < 0.9
            print(f"DEBUG - Aprobación: {approved}")
            
            if approved:
                # Actualizar pago como completado
                payment.status = 'completed'
                payment.transaction_id = f"TXN_{uuid.uuid4().hex[:8].upper()}"
                payment.processed_at = datetime.now()
                
                # Actualizar reserva
                booking.payment_status = 'paid'
                
                print(f"DEBUG - Pago aprobado: {payment.transaction_id}")
            else:
                # Actualizar pago como fallido
                payment.status = 'failed'
                payment.error_message = 'Tarjeta rechazada por el banco emisor'
                payment.processed_at = datetime.now()
                
                # Cancelar reserva
                booking.status = 'cancelled'
                booking.payment_status = 'failed'
                
                print(f"DEBUG - Pago rechazado")
            
            db.session.commit()
            print(f"DEBUG - Cambios guardados en base de datos")
            
            # Refrescar el objeto payment desde la base de datos
            db.session.refresh(payment)
            
            # Registrar auditoría
            log_audit(
                'deposit_payment_completed',
                resource_type='payment',
                resource_id=payment.id,
                details=f'Procesamiento de seña ${booking.deposit_amount} completado para reserva {booking_id}'
            )
            
            print(f"DEBUG - Estado final del pago: {payment.status}")
            print(f"DEBUG - Transaction ID: {payment.transaction_id}")
            
            return jsonify({
                'success': True,
                'message': 'Pago procesado',
                'payment_id': payment.id,
                'amount': booking.deposit_amount,
                'payment_status': payment.status,
                'transaction_id': payment.transaction_id
            })
            
        except Exception as e:
            print(f"DEBUG - Error procesando pago: {e}")
            return jsonify({
                'success': False,
                'message': 'Error al procesar pago',
                'error': str(e)
            }), 500
        
    except Exception as e:
        from config import db
        db.session.rollback()
        print(f"DEBUG - Error en procesamiento de pago: {str(e)}")
        print(f"DEBUG - Type de error: {type(e)}")
        import traceback
        print(f"DEBUG - Traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': 'Error al iniciar procesamiento de pago',
            'error': str(e)
        }), 400

@app.route('/api/payments/<int:payment_id>/status', methods=['GET'])
@login_required
def get_payment_status(payment_id):
    """Obtiene el estado de un pago"""
    try:
        payment = Payment.query.get_or_404(payment_id)
        
        # Verificar que el usuario sea el dueño del pago
        if payment.user_id != session['user_id']:
            return jsonify({
                'success': False,
                'message': 'No autorizado para ver este pago'
            }), 403
        
        return jsonify({
            'success': True,
            'payment': {
                'id': payment.id,
                'amount': payment.amount,
                'status': payment.status,
                'transaction_id': payment.transaction_id,
                'created_at': payment.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'processed_at': payment.processed_at.strftime('%Y-%m-%d %H:%M:%S') if payment.processed_at else None,
                'error_message': payment.error_message
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Error al obtener estado del pago',
            'error': str(e)
        }), 400

@app.route('/api/payments/user', methods=['GET'])
@login_required
def get_user_payments():
    """Obtiene todos los pagos del usuario actual"""
    try:
        payments = Payment.query.filter_by(user_id=session['user_id']).order_by(Payment.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'payments': [{
                'id': payment.id,
                'booking_id': payment.booking_id,
                'amount': payment.amount,
                'payment_type': payment.payment_type,
                'payment_method': payment.payment_method,
                'status': payment.status,
                'transaction_id': payment.transaction_id,
                'created_at': payment.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'processed_at': payment.processed_at.strftime('%Y-%m-%d %H:%M:%S') if payment.processed_at else None,
                'error_message': payment.error_message,
                'court_name': payment.booking.court.name if payment.booking and payment.booking.court else 'N/A'
            } for payment in payments]
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Error al obtener pagos',
            'error': str(e)
        }), 400
