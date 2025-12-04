from flask import render_template, jsonify, redirect, url_for, session, flash, request
from functools import wraps
from datetime import datetime, date, timedelta
from sqlalchemy import or_, and_, exc
from config import app, db, socketio
from models import User, Court, Booking, AuditLog, CriticalEvent, DataIntegrityReport, Payment
from models import log_audit, log_critical_event, detect_suspicious_activity
from models import LockManager, transaction_scope, add_sample_courts

# Decoradores de autenticación
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Debes iniciar sesión para acceder a esta página.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Debes iniciar sesión para acceder a esta página.', 'warning')
            return redirect(url_for('login'))
        
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin():
            flash('No tienes permisos de administrador.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def operator_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Debes iniciar sesión para acceder a esta página.', 'warning')
            return redirect(url_for('login'))
        
        user = User.query.get(session['user_id'])
        if not user or (not user.is_operator() and not user.is_admin()):
            flash('No tienes permisos de operador.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Rutas
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        ip_address = request.remote_addr
        
        # Detectar intentos múltiples fallidos
        if detect_suspicious_activity(ip_address, 'failed_login', threshold=3, time_window=300):
            flash('Demasiados intentos fallidos. Por favor espere 5 minutos.', 'danger')
            log_audit('login_blocked', details=f'IP {ip_address} bloqueada por múltiples intentos fallidos', success=False)
            return render_template('login.html')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            # Login exitoso
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            
            # Debug: imprimir información del usuario al hacer login
            print(f"LOGIN DEBUG - Usuario: {user.username}")
            print(f"LOGIN DEBUG - Rol asignado: {user.role}")
            print(f"LOGIN DEBUG - Email: {user.email}")
            
            # Registrar auditoría
            log_audit(
                'login_success',
                resource_type='user',
                resource_id=user.id,
                details=f'Usuario {username} inició sesión correctamente'
            )
            
            flash(f'Bienvenido {user.username}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            # Login fallido
            log_critical_event(
                'failed_login',
                f'Intento de login fallido para usuario: {username} desde IP: {ip_address}',
                'MEDIUM',
                {'username': username, 'ip_address': ip_address}
            )
            
            log_audit(
                'login_failed',
                details=f'Intento de login fallido para usuario: {username}',
                success=False,
                error_message='Credenciales inválidas'
            )
            
            flash('Usuario o contraseña incorrectos', 'danger')
            return render_template('login.html')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Asignar rol automáticamente según el email
        role = User.get_role_from_email(email)
        
        # Verificar si el usuario ya existe
        if User.query.filter_by(username=username).first():
            flash('El nombre de usuario ya está en uso.', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('El email ya está registrado.', 'danger')
            return render_template('register.html')
        
        # Crear nuevo usuario
        user = User(username=username, email=email, role=role)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        role_message = {
            'administrador': 'como Administrador',
            'operador': 'como Operador',
            'visitante': 'como Visitante'
        }
        
        flash(f'Registro exitoso. Tu cuenta ha sido creada {role_message[role]}.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente.', 'info')
    return redirect(url_for('index'))

@app.route('/')
def index():
    # Obtener canchas destacadas (en una aplicación real, podrías implementar lógica de destacados)
    featured_courts = Court.query.limit(4).all()
    
    # Si no hay canchas en la base de datos, agregar datos de ejemplo
    if not featured_courts:
        add_sample_courts()
        featured_courts = Court.query.limit(4).all()
    
    return render_template('index.html', courts=featured_courts)

@app.route('/api/courts')
def get_courts():
    courts = Court.query.all()
    return jsonify([{
        'id': court.id,
        'name': court.name,
        'location': court.location,
        'type': court.court_type,
        'price': court.price,
        'rating': court.rating,
        'image': court.image
    } for court in courts])

@app.route('/search')
def search():
    query = request.args.get('q', '')
    location = request.args.get('location', '')
    court_type = request.args.get('type', '')
    
    # Construir consulta
    query_builder = Court.query
    
    if query:
        query_builder = query_builder.filter(Court.name.ilike(f'%{query}%'))
    if location:
        query_builder = query_builder.filter(Court.location.ilike(f'%{location}%'))
    if court_type:
        query_builder = query_builder.filter(Court.court_type.ilike(f'%{court_type}%'))
    
    courts = query_builder.all()
    
    return jsonify([{
        'id': court.id,
        'name': court.name,
        'location': court.location,
        'type': court.court_type,
        'price': court.price,
        'rating': court.rating,
        'image': court.image
    } for court in courts])

@app.route('/book', methods=['POST'])
def book_court():
    data = request.get_json()
    court_id = data['court_id']
    booking_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
    start_time = datetime.strptime(data['start_time'], '%H:%M').time()
    end_time = datetime.strptime(data['end_time'], '%H:%M').time()
    
    # Resource ID para bloqueo
    resource_id = f"court_{court_id}_{booking_date}_{start_time}"
    
    try:
        # Adquirir bloqueo para evitar reservas simultáneas
        LockManager.acquire_lock(resource_id)
        
        # Verificar si la cancha existe (fuera de la transacción)
        court = db.session.query(Court).filter_by(id=court_id).first()
        if not court:
            return jsonify({'success': False, 'message': 'Cancha no encontrada'}), 404
        
        # Verificar si ya existe una reserva en el mismo horario (fuera de la transacción)
        existing_booking = db.session.query(Booking).filter(
            Booking.court_id == court_id,
            Booking.booking_date == booking_date,
            Booking.status != 'cancelled',
            or_(
                and_(Booking.start_time <= start_time, Booking.end_time > start_time),
                and_(Booking.start_time < end_time, Booking.end_time >= end_time),
                and_(Booking.start_time >= start_time, Booking.end_time <= end_time)
            )
        ).first()
        
        if existing_booking:
            return jsonify({
                'success': False, 
                'message': f'La cancha ya está reservada en ese horario por {existing_booking.user_name}'
            }), 409
        
        # Si el usuario está autenticado, usar su ID
        user_id = None
        user_name = data.get('name', '')
        user_email = data.get('email', '')
        
        if 'user_id' in session:
            user = db.session.query(User).filter_by(id=session['user_id']).first()
            if user:
                user_id = user.id
                user_name = user.username
                user_email = user.email
        
        # Calcular costo total y seña (50%)
        duration_hours = (datetime.combine(booking_date, end_time) - 
                         datetime.combine(booking_date, start_time)).total_seconds() / 3600
        total_amount = court.price * duration_hours
        deposit_amount = total_amount * 0.5  # 50% de seña
        
        # Crear la reserva
        booking = Booking(
            court_id=court_id,
            user_id=user_id,
            user_name=user_name,
            user_email=user_email,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            status='pending',
            total_amount=total_amount,
            deposit_amount=deposit_amount
        )
        
        db.session.add(booking)
        db.session.flush()  # Obtener ID sin commit final
        
        # Registrar auditoría
        log_audit(
            'create_booking',
            resource_type='booking',
            resource_id=booking.id,
            details=f'Reserva #{booking.id} para {court.name} el {booking_date} de {start_time} a {end_time}'
        )
        
        db.session.commit()
        
        # Emitir notificación en tiempo real
        socketio.emit('new_booking', {
            'booking_id': booking.id,
            'court_id': booking.court_id,
            'court_name': court.name,
            'user_name': booking.user_name,
            'date': data['date'],
            'start_time': data['start_time'],
            'end_time': data['end_time'],
            'created_at': booking.created_at.isoformat()
        }, room='admin_room')
        
        return jsonify({
            'success': True,
            'message': 'Reserva creada correctamente',
            'booking_id': booking.id,
            'total_amount': total_amount,
            'deposit_amount': deposit_amount,
            'requires_payment': True,
            'payment_deadline': '15 minutos'
        })
            
    except TimeoutError as e:
        return jsonify({
            'success': False,
            'message': 'El sistema está ocupado, por favor intenta nuevamente en unos segundos'
        }), 503
        
    except exc.IntegrityError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Error de integridad de datos, la reserva ya existe'
        }), 409
        
    except Exception as e:
        log_audit(
            'create_booking_failed',
            resource_type='booking',
            details=f'Error al crear reserva: {str(e)}',
            success=False,
            error_message=str(e)
        )
        return jsonify({
            'success': False,
            'message': 'Error al procesar la reserva'
        }), 500
        
    finally:
        # Liberar el bloqueo
        LockManager.release_lock(resource_id)

# Rutas adicionales según rol
@app.route('/dashboard')
@login_required
def dashboard():
    user = User.query.get(session['user_id'])
    
    # Debug: imprimir información del usuario
    print(f"DEBUG - Usuario: {user.username if user else 'None'}")
    print(f"DEBUG - Rol: {user.role if user else 'None'}")
    print(f"DEBUG - is_admin: {user.is_admin() if user else 'None'}")
    print(f"DEBUG - is_operator: {user.is_operator() if user else 'None'}")
    
    # Verificar si el usuario existe
    if not user:
        flash('Usuario no encontrado. Por favor, inicia sesión nuevamente.', 'error')
        session.clear()
        return redirect(url_for('login'))
    
    if user.is_admin():
        return render_template('admin.html', user=user)
    elif user.is_operator():
        return render_template('operador.html', user=user)
    else:
        return render_template('usuario.html', user=user)

@app.route('/profile')
@login_required
def profile():
    user = User.query.get(session['user_id'])
    
    # Verificar si el usuario existe
    if not user:
        flash('Usuario no encontrado. Por favor, inicia sesión nuevamente.', 'error')
        session.clear()
        return redirect(url_for('login'))
    
    return render_template('usuario.html', user=user)

# Endpoints REST API
@app.route('/api/courts/<int:court_id>', methods=['PUT'])
@operator_required
def update_court(court_id):
    """Actualiza una cancha existente"""
    try:
        data = request.get_json()
        
        court = Court.query.get(court_id)
        if not court:
            return jsonify({'success': False, 'message': 'Cancha no encontrada'}), 404
        
        # Actualizar campos
        if 'name' in data:
            court.name = data['name']
        if 'location' in data:
            court.location = data['location']
        if 'court_type' in data:
            court.court_type = data['court_type']
        if 'price' in data:
            court.price = float(data['price'])
        if 'description' in data:
            court.description = data['description']
        if 'image' in data:
            court.image = data['image']
        
        db.session.commit()
        
        # Registrar auditoría
        log_audit(
            'update_court',
            resource_type='court',
            resource_id=court.id,
            details=f'Cancha "{court.name}" actualizada'
        )
        
        return jsonify({
            'success': True,
            'message': 'Cancha actualizada correctamente',
            'court': {
                'id': court.id,
                'name': court.name,
                'location': court.location,
                'type': court.court_type,
                'price': court.price,
                'description': court.description,
                'image': court.image
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error actualizando cancha: {e}")
        return jsonify({'success': False, 'message': 'Error al actualizar cancha'}), 500

@app.route('/api/courts/<int:court_id>', methods=['DELETE'])
@operator_required
def delete_court(court_id):
    """Elimina una cancha"""
    try:
        court = Court.query.get(court_id)
        if not court:
            return jsonify({'success': False, 'message': 'Cancha no encontrada'}), 404
        
        # Verificar si hay reservas futuras
        future_bookings = Booking.query.filter(
            Booking.court_id == court_id,
            Booking.booking_date >= date.today(),
            Booking.status != 'cancelled'
        ).count()
        
        if future_bookings > 0:
            return jsonify({
                'success': False, 
                'message': f'No se puede eliminar la cancha. Tiene {future_bookings} reservas futuras.'
            }), 400
        
        court_name = court.name
        db.session.delete(court)
        db.session.commit()
        
        # Registrar auditoría
        log_audit(
            'delete_court',
            resource_type='court',
            resource_id=court_id,
            details=f'Cancha "{court_name}" eliminada'
        )
        
        return jsonify({
            'success': True,
            'message': 'Cancha eliminada correctamente'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error eliminando cancha: {e}")
        return jsonify({'success': False, 'message': 'Error al eliminar cancha'}), 500

@app.route('/api/courts', methods=['POST'])
@operator_required
def create_court():
    data = request.get_json()
    
    try:
        # Validar datos de entrada
        if not data.get('name') or not data.get('location') or not data.get('court_type'):
            log_audit(
                'create_court_failed',
                resource_type='court',
                details='Datos incompletos para crear cancha',
                success=False,
                error_message='Faltan campos requeridos'
            )
            return jsonify({
                'success': False,
                'message': 'Faltan campos requeridos',
                'error': 'Faltan name, location, o court_type'
            }), 400
        
        court = Court(
            name=data['name'],
            location=data['location'],
            court_type=data['court_type'],
            price=data['price'],
            rating=data.get('rating', 0),
            image=data.get('image', ''),
            description=data.get('description', '')
        )
        
        db.session.add(court)
        db.session.commit()
        
        # Registrar auditoría
        log_audit(
            'create_court',
            resource_type='court',
            resource_id=court.id,
            details=f'Cancha "{court.name}" creada en {court.location}'
        )
        
        # Notificar a administradores
        socketio.emit('court_added', {
            'court_id': court.id,
            'court_name': court.name,
            'added_by': session.get('username', 'Unknown')
        }, room='admin_room')
        
        return jsonify({
            'success': True,
            'message': 'Cancha agregada correctamente',
            'court_id': court.id
        })
    except Exception as e:
        log_audit(
            'create_court_failed',
            resource_type='court',
            details=f'Error al crear cancha: {str(e)}',
            success=False,
            error_message=str(e)
        )
        
        # Detectar posible inserción de datos inválidos
        if 'invalid' in str(e).lower() or 'constraint' in str(e).lower():
            log_critical_event(
                'invalid_data_insertion',
                f'Intento de inserción de datos inválidos en creación de cancha: {str(e)}',
                'HIGH',
                {'error': str(e), 'data': data}
            )
        
        return jsonify({
            'success': False,
            'message': 'Error al agregar cancha',
            'error': str(e)
        }), 400

@app.route('/api/courts/<int:court_id>', methods=['GET'])
def get_court(court_id):
    court = Court.query.get_or_404(court_id)
    return jsonify({
        'id': court.id,
        'name': court.name,
        'location': court.location,
        'type': court.court_type,
        'price': court.price,
        'rating': court.rating,
        'image': court.image,
        'description': court.description
    })

@app.route('/api/courts/<int:court_id>/schedule', methods=['GET'])
@operator_required
def get_court_schedule(court_id):
    """Obtiene el horario de una cancha específica"""
    try:
        # Obtener fecha actual y próxima semana
        today = date.today()
        end_date = today + timedelta(days=7)
        
        # Obtener todas las reservas de la cancha en los próximos 7 días
        bookings = Booking.query.filter(
            Booking.court_id == court_id,
            Booking.booking_date >= today,
            Booking.booking_date <= end_date,
            Booking.status != 'cancelled'
        ).order_by(Booking.booking_date, Booking.start_time).all()
        
        # Obtener información de la cancha
        court = Court.query.get(court_id)
        if not court:
            return jsonify({'success': False, 'message': 'Cancha no encontrada'}), 404
        
        # Formatear las reservas
        schedule = []
        for booking in bookings:
            schedule.append({
                'id': booking.id,
                'date': booking.booking_date.strftime('%Y-%m-%d'),
                'start_time': booking.start_time.strftime('%H:%M'),
                'end_time': booking.end_time.strftime('%H:%M'),
                'user_name': booking.user_name,
                'user_email': booking.user_email,
                'status': booking.status,
                'payment_status': booking.payment_status
            })
        
        return jsonify({
            'success': True,
            'court': {
                'id': court.id,
                'name': court.name,
                'price': court.price
            },
            'schedule': schedule,
            'date_range': {
                'start': today.strftime('%Y-%m-%d'),
                'end': end_date.strftime('%Y-%m-%d')
            }
        })
        
    except Exception as e:
        print(f"Error obteniendo horario de cancha: {e}")
        return jsonify({'success': False, 'message': 'Error al obtener horario'}), 500

@app.route('/api/bookings', methods=['GET'])
@login_required
def get_bookings():
    user = User.query.get(session['user_id'])
    
    if user.is_admin():
        bookings = Booking.query.all()
    elif user.is_operator():
        bookings = Booking.query.all()
    else:
        # Buscar reservas por user_id o por user_name (para compatibilidad)
        bookings = Booking.query.filter(
            (Booking.user_id == user.id) | 
            (Booking.user_name == user.username)
        ).all()
    
    return jsonify([{
        'id': booking.id,
        'court_id': booking.court_id,
        'court_name': booking.court.name if booking.court else 'N/A',
        'user_name': booking.user_name,
        'user_email': booking.user_email,
        'date': booking.booking_date.strftime('%Y-%m-%d'),
        'start_time': booking.start_time.strftime('%H:%M'),
        'end_time': booking.end_time.strftime('%H:%M'),
        'status': booking.status,
        'payment_status': booking.payment_status,
        'total_amount': booking.total_amount,
        'deposit_amount': booking.deposit_amount,
        'created_at': booking.created_at.strftime('%Y-%m-%d %H:%M:%S')
    } for booking in bookings])

@app.route('/api/bookings/<int:booking_id>', methods=['PUT'])
@operator_required
def update_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    data = request.get_json()
    
    if 'status' in data:
        booking.status = data['status']
        db.session.commit()
        
        # Emitir notificación de actualización
        socketio.emit('booking_updated', {
            'booking_id': booking.id,
            'status': booking.status,
            'court_name': booking.court.name if booking.court else 'N/A'
        }, room='admin_room')
        
        return jsonify({
            'success': True,
            'message': 'Reserva actualizada correctamente'
        })
    
    return jsonify({
        'success': False,
        'message': 'Datos inválidos'
    }), 400

@app.route('/api/bookings/<int:booking_id>', methods=['DELETE'])
@admin_required
def delete_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    
    try:
        # Guardar información antes de eliminar
        booking_info = {
            'booking_id': booking.id,
            'user_name': booking.user_name,
            'court_name': booking.court.name if booking.court else 'N/A',
            'date': booking.booking_date.strftime('%Y-%m-%d'),
            'start_time': booking.start_time.strftime('%H:%M')
        }
        
        # Registrar auditoría antes de eliminar
        log_audit(
            'delete_booking',
            resource_type='booking',
            resource_id=booking.id,
            details=f'Eliminada reserva #{booking.id} de {booking.user_name} para {booking_info["court_name"]}'
        )
        
        db.session.delete(booking)
        db.session.commit()
        
        # Notificar eliminación
        socketio.emit('booking_deleted', {
            'booking_id': booking_info['booking_id'],
            'user_name': booking_info['user_name'],
            'court_name': booking_info['court_name'],
            'date': booking_info['date'],
            'start_time': booking_info['start_time'],
            'deleted_by': session.get('username', 'Admin')
        }, room='admin_room')
        
        return jsonify({
            'success': True,
            'message': 'Reserva eliminada correctamente'
        })
    except Exception as e:
        log_audit(
            'delete_booking_failed',
            resource_type='booking',
            resource_id=booking_id,
            details=f'Error al eliminar reserva: {str(e)}',
            success=False,
            error_message=str(e)
        )
        
        return jsonify({
            'success': False,
            'message': 'Error al eliminar reserva',
            'error': str(e)
        }), 400

@app.route('/api/audit-logs', methods=['GET'])
@admin_required
def get_audit_logs():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    # Filtrar por usuario si se especifica
    user_filter = request.args.get('user_id')
    query = AuditLog.query
    
    if user_filter:
        query = query.filter(AuditLog.user_id == user_filter)
    
    # Ordenar por fecha descendente
    logs = query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'logs': [{
            'id': log.id,
            'username': log.username,
            'action': log.action,
            'resource_type': log.resource_type,
            'resource_id': log.resource_id,
            'details': log.details,
            'ip_address': log.ip_address,
            'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'success': log.success,
            'error_message': log.error_message
        } for log in logs.items],
        'pagination': {
            'page': logs.page,
            'pages': logs.pages,
            'per_page': logs.per_page,
            'total': logs.total
        }
    })

@app.route('/api/critical-events', methods=['GET'])
@admin_required
def get_critical_events():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    # Filtrar por tipo si se especifica
    event_type = request.args.get('event_type')
    query = CriticalEvent.query
    
    if event_type:
        query = query.filter(CriticalEvent.event_type == event_type)
    
    # Ordenar por fecha descendente
    events = query.order_by(CriticalEvent.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'events': [{
            'id': event.id,
            'event_type': event.event_type,
            'description': event.description,
            'severity': event.severity,
            'ip_address': event.ip_address,
            'timestamp': event.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'resolved': event.resolved,
            'resolved_by': event.resolver.username if event.resolver else None,
            'resolved_at': event.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if event.resolved_at else None,
            'additional_data': json.loads(event.additional_data) if event.additional_data else None
        } for event in events.items],
        'pagination': {
            'page': events.page,
            'pages': events.pages,
            'per_page': events.per_page,
            'total': events.total
        }
    })

@app.route('/api/integrity-check', methods=['POST'])
@admin_required
def integrity_check():
    """Ejecuta verificación de integridad de datos"""
    from models import run_integrity_check
    result = run_integrity_check()
    return jsonify(result)

@app.route('/api/integrity-reports', methods=['GET'])
@admin_required
def get_integrity_reports():
    """Obtiene reportes de integridad"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    status_filter = request.args.get('status')
    
    query = DataIntegrityReport.query
    
    if status_filter:
        query = query.filter(DataIntegrityReport.status == status_filter)
    
    reports = query.order_by(DataIntegrityReport.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'reports': [{
            'id': report.id,
            'check_type': report.check_type,
            'table_name': report.table_name,
            'issue_description': report.issue_description,
            'severity': report.severity,
            'affected_records': report.affected_records,
            'auto_fix_available': report.auto_fix_available,
            'fix_description': report.fix_description,
            'status': report.status,
            'created_at': report.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'fixed_at': report.fixed_at.strftime('%Y-%m-%d %H:%M:%S') if report.fixed_at else None,
            'fixed_by': report.fixer.username if report.fixer else None
        } for report in reports.items],
        'pagination': {
            'page': reports.page,
            'pages': reports.pages,
            'per_page': reports.per_page,
            'total': reports.total
        }
    })

@app.route('/api/integrity-fix/<int:issue_id>', methods=['POST'])
@admin_required
def fix_integrity_issue_endpoint(issue_id):
    """Aplica corrección a un problema de integridad"""
    from models import fix_integrity_issue
    result = fix_integrity_issue(issue_id)
    return jsonify(result)

@app.route('/api/integrity-ignore/<int:issue_id>', methods=['POST'])
@admin_required
def ignore_integrity_issue(issue_id):
    """Marca un problema como ignorado"""
    try:
        issue = DataIntegrityReport.query.get_or_404(issue_id)
        issue.status = 'ignored'
        
        db.session.commit()
        
        # Registrar auditoría
        log_audit(
            'integrity_ignore',
            resource_type='data_integrity',
            resource_id=issue.id,
            details=f'Problema de integridad ignorado: {issue.issue_description}'
        )
        
        return jsonify({
            'success': True,
            'message': 'Problema marcado como ignorado'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/integrity-stats', methods=['GET'])
@admin_required
def get_integrity_stats():
    """Obtiene estadísticas de integridad"""
    try:
        total_issues = DataIntegrityReport.query.count()
        detected_issues = DataIntegrityReport.query.filter_by(status='detected').count()
        fixed_issues = DataIntegrityReport.query.filter_by(status='fixed').count()
        ignored_issues = DataIntegrityReport.query.filter_by(status='ignored').count()
        
        # Contar por severidad
        critical_count = DataIntegrityReport.query.filter_by(severity='CRITICAL', status='detected').count()
        high_count = DataIntegrityReport.query.filter_by(severity='HIGH', status='detected').count()
        medium_count = DataIntegrityReport.query.filter_by(severity='MEDIUM', status='detected').count()
        low_count = DataIntegrityReport.query.filter_by(severity='LOW', status='detected').count()
        
        return jsonify({
            'total_issues': total_issues,
            'detected_issues': detected_issues,
            'fixed_issues': fixed_issues,
            'ignored_issues': ignored_issues,
            'severity_breakdown': {
                'critical': critical_count,
                'high': high_count,
                'medium': medium_count,
                'low': low_count
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/current-user', methods=['GET'])
@login_required
def get_current_user():
    """Obtiene información del usuario actual"""
    try:
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role,
                'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else None
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    """Obtiene lista de usuarios"""
    try:
        users = User.query.all()
        return jsonify({
            'users': [{
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role,
                'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else None
            } for user in users]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
