from flask import session, request, flash, redirect, url_for
from flask_socketio import emit
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
from sqlalchemy import or_, and_, exc
from contextlib import contextmanager
import threading
import time
from config import app, db, socketio, critical_logger

# Modelos de Base de Datos
class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    username = db.Column(db.String(80), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50), nullable=True)  # user, court, booking, etc.
    resource_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    success = db.Column(db.Boolean, default=True)
    error_message = db.Column(db.Text, nullable=True)
    
    # Relación
    user = db.relationship('User', backref='audit_logs')

class DataIntegrityReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    check_type = db.Column(db.String(50), nullable=False)  # foreign_keys, counts, formats
    table_name = db.Column(db.String(50), nullable=False)
    issue_description = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20), default='MEDIUM')  # LOW, MEDIUM, HIGH, CRITICAL
    affected_records = db.Column(db.Text, nullable=True)  # JSON con IDs afectados
    auto_fix_available = db.Column(db.Boolean, default=False)
    fix_description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='detected')  # detected, fixed, ignored
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    fixed_at = db.Column(db.DateTime, nullable=True)
    fixed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # Relación
    fixer = db.relationship('User', foreign_keys=[fixed_by])

class CriticalEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(50), nullable=False)  # failed_login, unauthorized_access, etc.
    description = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20), default='HIGH')  # LOW, MEDIUM, HIGH, CRITICAL
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    additional_data = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    resolved = db.Column(db.Boolean, default=False)
    resolved_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    
    # Relación
    resolver = db.relationship('User', foreign_keys=[resolved_by])

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), default='visitante')  # visitante, operador, administrador
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self):
        return self.role == 'administrador'
    
    def is_operator(self):
        return self.role == 'operador'
    
    @staticmethod
    def get_role_from_email(email):
        """Asignar rol según el dominio del email"""
        print(f"EMAIL DEBUG - Email recibido: {email}")
        if email.endswith('@golistica.com'):
            print(f"EMAIL DEBUG - Asignando rol: administrador")
            return 'administrador'
        elif email.endswith('@operador.golistica.com'):
            print(f"EMAIL DEBUG - Asignando rol: operador")
            return 'operador'
        else:
            print(f"EMAIL DEBUG - Asignando rol: visitante")
            return 'visitante'

class Court(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    court_type = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    rating = db.Column(db.Float, default=0)
    image = db.Column(db.String(300))
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    court_id = db.Column(db.Integer, db.ForeignKey('court.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Ahora relacionado con User
    user_name = db.Column(db.String(100), nullable=True)  # Mantener para compatibilidad
    user_email = db.Column(db.String(120), nullable=True)  # Mantener para compatibilidad
    booking_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, cancelled
    payment_status = db.Column(db.String(20), default='pending')  # pending, paid, refunded
    total_amount = db.Column(db.Float, nullable=False)
    deposit_amount = db.Column(db.Float, nullable=False)
    
    # Relaciones
    user = db.relationship('User', backref='bookings')
    court = db.relationship('Court', backref='bookings')
    payments = db.relationship('Payment', backref='booking', lazy=True)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_type = db.Column(db.String(20), default='deposit')  # deposit, full, refund
    payment_method = db.Column(db.String(50), nullable=True)  # credit_card, debit_card, cash, transfer
    transaction_id = db.Column(db.String(100), nullable=True)  # ID de transacción externa
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed, refunded
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    
    # Relaciones
    user = db.relationship('User', backref='payments')

# Gestor de transacciones para concurrencia
@contextmanager
def transaction_scope():
    """Context manager para transacciones con manejo de concurrencia"""
    transaction = db.session.begin_nested()
    try:
        yield db.session
        transaction.commit()
    except Exception as e:
        transaction.rollback()
        db.session.rollback()
        raise e
    finally:
        db.session.close()

# Lock manager para recursos críticos
class LockManager:
    _locks = {}
    _lock = threading.Lock()
    
    @classmethod
    def acquire_lock(cls, resource_id, timeout=30):
        """Adquiere un bloqueo para un recurso"""
        with cls._lock:
            if resource_id in cls._locks:
                # Esperar a que se libere el bloqueo
                start_time = time.time()
                while resource_id in cls._locks and (time.time() - start_time) < timeout:
                    time.sleep(0.1)
                
                if resource_id in cls._locks:
                    raise TimeoutError(f"No se pudo adquirir bloqueo para {resource_id}")
            
            cls._locks[resource_id] = threading.current_thread().ident
            return True
    
    @classmethod
    def release_lock(cls, resource_id):
        """Libera un bloqueo"""
        with cls._lock:
            if resource_id in cls._locks:
                del cls._locks[resource_id]

# Funciones de integridad de datos
def check_foreign_keys():
    """Verifica integridad de claves foráneas"""
    issues = []
    
    # Verificar bookings con court_id inválido
    orphan_bookings = db.session.query(Booking).filter(
        ~Booking.court_id.in_(db.session.query(Court.id))
    ).all()
    
    if orphan_bookings:
        issues.append({
            'check_type': 'foreign_keys',
            'table_name': 'bookings',
            'issue_description': f'Reservas con court_id inválido: {len(orphan_bookings)} registros',
            'severity': 'HIGH',
            'affected_records': json.dumps([b.id for b in orphan_bookings]),
            'auto_fix_available': True,
            'fix_description': 'Eliminar reservas huérfanas o marcar como canceladas'
        })
    
    # Verificar bookings con user_id inválido
    orphan_user_bookings = db.session.query(Booking).filter(
        Booking.user_id.isnot(None),
        ~Booking.user_id.in_(db.session.query(User.id))
    ).all()
    
    if orphan_user_bookings:
        issues.append({
            'check_type': 'foreign_keys',
            'table_name': 'bookings',
            'issue_description': f'Reservas con user_id inválido: {len(orphan_user_bookings)} registros',
            'severity': 'MEDIUM',
            'affected_records': json.dumps([b.id for b in orphan_user_bookings]),
            'auto_fix_available': True,
            'fix_description': 'Limpiar user_id de reservas huérfanas'
        })
    
    return issues

def check_data_consistency():
    """Verifica consistencia de datos"""
    issues = []
    
    # Verificar fechas de reservas en el pasado
    past_bookings = db.session.query(Booking).filter(
        Booking.booking_date < datetime.now().date(),
        Booking.status == 'pending'
    ).all()
    
    if past_bookings:
        issues.append({
            'check_type': 'data_consistency',
            'table_name': 'bookings',
            'issue_description': f'Reservas pendientes con fecha pasada: {len(past_bookings)} registros',
            'severity': 'MEDIUM',
            'affected_records': json.dumps([b.id for b in past_bookings]),
            'auto_fix_available': True,
            'fix_description': 'Marcar reservas vencidas como canceladas automáticamente'
        })
    
    # Verificar usuarios sin email válido
    invalid_emails = db.session.query(User).filter(
        or_(User.email.is_(None), User.email == '', ~User.email.like('%@%'))
    ).all()
    
    if invalid_emails:
        issues.append({
            'check_type': 'data_consistency',
            'table_name': 'users',
            'issue_description': f'Usuarios con email inválido: {len(invalid_emails)} registros',
            'severity': 'LOW',
            'affected_records': json.dumps([u.id for u in invalid_emails]),
            'auto_fix_available': False,
            'fix_description': 'Revisar manualmente y corregir emails inválidos'
        })
    
    return issues

def check_format_validation():
    """Verifica formatos de datos"""
    issues = []
    
    # Verificar precios negativos en canchas
    negative_prices = db.session.query(Court).filter(Court.price < 0).all()
    
    if negative_prices:
        issues.append({
            'check_type': 'formats',
            'table_name': 'courts',
            'issue_description': f'Canchas con precio negativo: {len(negative_prices)} registros',
            'severity': 'HIGH',
            'affected_records': json.dumps([c.id for c in negative_prices]),
            'auto_fix_available': True,
            'fix_description': 'Corregir precios negativos a valor positivo o eliminar canchas'
        })
    
    # Verificar ratings fuera de rango
    invalid_ratings = db.session.query(Court).filter(
        or_(Court.rating < 0, Court.rating > 5)
    ).all()
    
    if invalid_ratings:
        issues.append({
            'check_type': 'formats',
            'table_name': 'courts',
            'issue_description': f'Canchas con rating fuera de rango (0-5): {len(invalid_ratings)} registros',
            'severity': 'LOW',
            'affected_records': json.dumps([c.id for c in invalid_ratings]),
            'auto_fix_available': True,
            'fix_description': 'Ajustar ratings a rango válido (0-5)'
        })
    
    return issues

def run_integrity_check():
    """Ejecuta todas las verificaciones de integridad"""
    all_issues = []
    
    try:
        # Ejecutar todas las verificaciones
        all_issues.extend(check_foreign_keys())
        all_issues.extend(check_data_consistency())
        all_issues.extend(check_format_validation())
        
        # Guardar resultados en la base de datos
        for issue in all_issues:
            # Verificar si ya existe un reporte similar
            existing = DataIntegrityReport.query.filter_by(
                check_type=issue['check_type'],
                table_name=issue['table_name'],
                status='detected'
            ).first()
            
            if not existing:
                report = DataIntegrityReport(**issue)
                db.session.add(report)
        
        db.session.commit()
        
        # Registrar auditoría
        log_audit(
            'integrity_check',
            details=f'Verificación de integridad completada: {len(all_issues)} problemas detectados'
        )
        
        return {
            'success': True,
            'issues_found': len(all_issues),
            'issues': all_issues
        }
        
    except Exception as e:
        log_audit(
            'integrity_check_failed',
            details=f'Error en verificación de integridad: {str(e)}',
            success=False
        )
        return {
            'success': False,
            'error': str(e)
        }

def fix_integrity_issue(issue_id, auto_fix=False):
    """Aplica corrección a un problema de integridad"""
    try:
        issue = DataIntegrityReport.query.get_or_404(issue_id)
        
        if issue.check_type == 'foreign_keys' and issue.table_name == 'bookings':
            affected_ids = json.loads(issue.affected_records) if issue.affected_records else []
            
            if 'court_id inválido' in issue.issue_description:
                # Marcar reservas como canceladas
                bookings = Booking.query.filter(Booking.id.in_(affected_ids)).all()
                for booking in bookings:
                    booking.status = 'cancelled'
                    booking.user_name = booking.user_name or 'Sistema'
                    booking.user_email = booking.user_email or 'corrupto@ejemplo.com'
                
            elif 'user_id inválido' in issue.issue_description:
                # Limpiar user_id
                bookings = Booking.query.filter(Booking.id.in_(affected_ids)).all()
                for booking in bookings:
                    booking.user_id = None
        
        elif issue.check_type == 'data_consistency' and 'fecha pasada' in issue.issue_description:
            affected_ids = json.loads(issue.affected_records) if issue.affected_records else []
            bookings = Booking.query.filter(Booking.id.in_(affected_ids)).all()
            for booking in bookings:
                booking.status = 'cancelled'
        
        elif issue.check_type == 'formats' and issue.table_name == 'courts':
            affected_ids = json.loads(issue.affected_records) if issue.affected_records else []
            courts = Court.query.filter(Court.id.in_(affected_ids)).all()
            
            for court in courts:
                if court.price < 0:
                    court.price = abs(court.price)
                if court.rating < 0:
                    court.rating = 0
                elif court.rating > 5:
                    court.rating = 5
        
        # Actualizar estado del issue
        issue.status = 'fixed'
        issue.fixed_at = datetime.utcnow()
        issue.fixed_by = session.get('user_id')
        
        db.session.commit()
        
        # Registrar auditoría
        log_audit(
            'integrity_fix',
            resource_type='data_integrity',
            resource_id=issue.id,
            details=f'Corregido problema de integridad: {issue.issue_description}'
        )
        
        return {
            'success': True,
            'message': 'Problema corregido correctamente'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def log_audit(action, resource_type=None, resource_id=None, details=None, success=True, error_message=None):
    """Registra acciones de auditoría"""
    try:
        user_id = session.get('user_id') if 'user_id' in session else None
        username = session.get('username') if 'username' in session else None
        
        audit_log = AuditLog(
            user_id=user_id,
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', ''),
            success=success,
            error_message=error_message
        )
        
        db.session.add(audit_log)
        db.session.commit()
        
        # También registrar en el log de la aplicación
        log_message = f"AUDIT: {action} by {username or 'Anonymous'}"
        if resource_type and resource_id:
            log_message += f" on {resource_type}:{resource_id}"
        if details:
            log_message += f" - {details}"
        if not success:
            log_message += f" - FAILED: {error_message}"
            
        app.logger.info(log_message)
        
    except Exception as e:
        app.logger.error(f"Error en auditoría: {str(e)}")

def log_critical_event(event_type, description, severity='HIGH', additional_data=None):
    """Registra eventos críticos y envía notificaciones"""
    try:
        critical_event = CriticalEvent(
            event_type=event_type,
            description=description,
            severity=severity,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', ''),
            additional_data=json.dumps(additional_data) if additional_data else None
        )
        
        db.session.add(critical_event)
        db.session.commit()
        
        # Registrar en log crítico
        critical_logger.critical(f"{event_type}: {description}")
        
        # Enviar notificación en tiempo real a administradores
        socketio.emit('critical_event', {
            'event_type': event_type,
            'description': description,
            'severity': severity,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'ip_address': request.remote_addr
        }, room='admin_room')
        
        # Si es crítico, también enviar al log principal
        if severity in ['HIGH', 'CRITICAL']:
            app.logger.critical(f"CRITICAL EVENT: {event_type} - {description}")
            
    except Exception as e:
        app.logger.error(f"Error en evento crítico: {str(e)}")

def detect_suspicious_activity(ip_address, event_type, threshold=5, time_window=300):
    """Detecta actividad sospechosa basada en frecuencia"""
    try:
        time_threshold = datetime.utcnow() - timedelta(seconds=time_window)
        
        # Contar eventos recientes desde la misma IP
        recent_events = CriticalEvent.query.filter(
            CriticalEvent.ip_address == ip_address,
            CriticalEvent.event_type == event_type,
            CriticalEvent.timestamp >= time_threshold
        ).count()
        
        if recent_events >= threshold:
            log_critical_event(
                'suspicious_activity',
                f'Detección de actividad sospechosa: {recent_events} eventos {event_type} en {time_window} segundos desde IP {ip_address}',
                'CRITICAL',
                {'event_count': recent_events, 'time_window': time_window}
            )
            return True
            
    except Exception as e:
        app.logger.error(f"Error en detección de actividad sospechosa: {str(e)}")
    
    return False

def create_admin_user():
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            email='admin@golistica.com',
            role='administrador'
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print('Usuario administrador creado: admin/admin123')

def add_sample_courts():
    if Court.query.count() == 0:
        sample_courts = [
            # Fútbol 5 - Barrios de CABA
            {
                'name': 'Cancha La 5 de Palermo',
                'location': 'Palermo, CABA',
                'court_type': 'Fútbol 5',
                'price': 2800,
                'rating': 4.8,
                'image': 'https://images.unsplash.com/photo-1540747913346-19e32dc3d97b?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 5 sintética con iluminación LED y vestuarios completos.'
            },
            {
                'name': 'Cancha 5 Estrellas Recoleta',
                'location': 'Recoleta, CABA',
                'court_type': 'Fútbol 5',
                'price': 3200,
                'rating': 4.9,
                'image': 'https://images.unsplash.com/photo-1517466787929-bc90951d0974?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 5 profesional con césped de última generación.'
            },
            {
                'name': 'La Canchita de Belgrano',
                'location': 'Belgrano, CABA',
                'court_type': 'Fútbol 5',
                'price': 2600,
                'rating': 4.7,
                'image': 'https://images.unsplash.com/photo-1554068393-54bef91d03b3?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 5 con techado y excelente iluminación.'
            },
            {
                'name': '5 de Caballito',
                'location': 'Caballito, CABA',
                'court_type': 'Fútbol 5',
                'price': 2400,
                'rating': 4.6,
                'image': 'https://images.unsplash.com/photo-1540747913346-19e32dc3d97b?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 5 sintética con vestuarios y duchas.'
            },
            {
                'name': 'Cancha Villa Urquiza F5',
                'location': 'Villa Urquiza, CABA',
                'court_type': 'Fútbol 5',
                'price': 2200,
                'rating': 4.5,
                'image': 'https://images.unsplash.com/photo-1517466787929-bc90951d0974?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 5 con césped artificial y buena iluminación.'
            },
            {
                'name': 'La 5 de Almagro',
                'location': 'Almagro, CABA',
                'court_type': 'Fútbol 5',
                'price': 2500,
                'rating': 4.7,
                'image': 'https://images.unsplash.com/photo-1554068393-54bef91d03b3?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 5 con superficie profesional y vestuarios.'
            },
            {
                'name': 'Cancha 5 Flores',
                'location': 'Flores, CABA',
                'court_type': 'Fútbol 5',
                'price': 2100,
                'rating': 4.4,
                'image': 'https://images.unsplash.com/photo-1540747913346-19e32dc3d97b?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 5 económica con buenas instalaciones.'
            },
            {
                'name': 'La 5 de Barracas',
                'location': 'Barracas, CABA',
                'court_type': 'Fútbol 5',
                'price': 2000,
                'rating': 4.3,
                'image': 'https://images.unsplash.com/photo-1517466787929-bc90951d0974?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 5 con iluminación y acceso fácil.'
            },
            
            # Fútbol 7 - Barrios de CABA
            {
                'name': 'Cancha 7 de Palermo',
                'location': 'Palermo, CABA',
                'court_type': 'Fútbol 7',
                'price': 4500,
                'rating': 4.9,
                'image': 'https://images.unsplash.com/photo-1517466787929-bc90951d0974?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 7 con césped sintético de alta calidad y vestuarios.'
            },
            {
                'name': '7 Estrellas Belgrano',
                'location': 'Belgrano, CABA',
                'court_type': 'Fútbol 7',
                'price': 4800,
                'rating': 4.8,
                'image': 'https://images.unsplash.com/photo-1554068393-54bef91d03b3?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 7 profesional con medidas reglamentarias.'
            },
            {
                'name': 'La 7 de Recoleta',
                'location': 'Recoleta, CABA',
                'court_type': 'Fútbol 7',
                'price': 5000,
                'rating': 4.9,
                'image': 'https://images.unsplash.com/photo-1517466787929-bc90951d0974?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 7 con césped premium e iluminación LED.'
            },
            {
                'name': 'Cancha 7 de Caballito',
                'location': 'Caballito, CABA',
                'court_type': 'Fútbol 7',
                'price': 4200,
                'rating': 4.6,
                'image': 'https://images.unsplash.com/photo-1554068393-54bef91d03b3?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 7 con excelente superficie y vestuarios completos.'
            },
            {
                'name': '7 de Villa Crespo',
                'location': 'Villa Crespo, CABA',
                'court_type': 'Fútbol 7',
                'price': 4000,
                'rating': 4.5,
                'image': 'https://images.unsplash.com/photo-1517466787929-bc90951d0974?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 7 con césped sintético y buena iluminación.'
            },
            {
                'name': 'La 7 de Nuñez',
                'location': 'Nuñez, CABA',
                'court_type': 'Fútbol 7',
                'price': 4300,
                'rating': 4.7,
                'image': 'https://images.unsplash.com/photo-1517466787929-bc90951d0974?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 7 con instalaciones profesionales.'
            },
            {
                'name': 'Cancha 7 de Almagro',
                'location': 'Almagro, CABA',
                'court_type': 'Fútbol 7',
                'price': 4100,
                'rating': 4.6,
                'image': 'https://images.unsplash.com/photo-1517466787929-bc90951d0974?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 7 con césped artificial y vestuarios.'
            },
            {
                'name': '7 de Flores',
                'location': 'Flores, CABA',
                'court_type': 'Fútbol 7',
                'price': 3800,
                'rating': 4.4,
                'image': 'https://images.unsplash.com/photo-1517466787929-bc90951d0974?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 7 económica con buenas instalaciones.'
            },
            
            # Fútbol 11 - Barrios de CABA
            {
                'name': 'Cancha 11 de Palermo',
                'location': 'Palermo, CABA',
                'court_type': 'Fútbol 11',
                'price': 8000,
                'rating': 4.9,
                'image': 'https://images.unsplash.com/photo-1517466787929-bc90951d0974?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 11 reglamentaria con césped sintético profesional.'
            },
            {
                'name': '11 de Belgrano',
                'location': 'Belgrano, CABA',
                'court_type': 'Fútbol 11',
                'price': 8500,
                'rating': 4.8,
                'image': 'https://images.unsplash.com/photo-1517466787929-bc90951d0974?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 11 con medidas oficiales y excelente césped.'
            },
            {
                'name': 'La 11 de Recoleta',
                'location': 'Recoleta, CABA',
                'court_type': 'Fútbol 11',
                'price': 9000,
                'rating': 5.0,
                'image': 'https://images.unsplash.com/photo-1517466787929-bc90951d0974?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 11 premium con césped de última generación.'
            },
            {
                'name': 'Cancha 11 de Caballito',
                'location': 'Caballito, CABA',
                'court_type': 'Fútbol 11',
                'price': 7500,
                'rating': 4.7,
                'image': 'https://images.unsplash.com/photo-1517466787929-bc90951d0974?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 11 con césped sintético y vestuarios completos.'
            },
            {
                'name': '11 de Villa Devoto',
                'location': 'Villa Devoto, CABA',
                'court_type': 'Fútbol 11',
                'price': 7000,
                'rating': 4.6,
                'image': 'https://images.unsplash.com/photo-1517466787929-bc90951d0974?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 11 con buenas instalaciones y acceso fácil.'
            },
            {
                'name': 'La 11 de Nuñez',
                'location': 'Nuñez, CABA',
                'court_type': 'Fútbol 11',
                'price': 7800,
                'rating': 4.8,
                'image': 'https://images.unsplash.com/photo-1517466787929-bc90951d0974?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 11 con césped profesional e iluminación.'
            },
            {
                'name': '11 de Constitución',
                'location': 'Constitución, CABA',
                'court_type': 'Fútbol 11',
                'price': 6500,
                'rating': 4.4,
                'image': 'https://images.unsplash.com/photo-1517466787929-bc90951d0974?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 11 económica con buenas condiciones.'
            },
            {
                'name': 'Cancha 11 de Mataderos',
                'location': 'Mataderos, CABA',
                'court_type': 'Fútbol 11',
                'price': 6000,
                'rating': 4.3,
                'image': 'https://images.unsplash.com/photo-1517466787929-bc90951d0974?ixlib=rb-1.2.1&auto=format&fit=crop&w=600&q=80',
                'description': 'Cancha de fútbol 11 con césped sintético y vestuarios.'
            }
        ]
        
        for court_data in sample_courts:
            court = Court(**court_data)
            db.session.add(court)
        
        db.session.commit()
        print('Canchas de ejemplo agregadas')

# Crear tablas de base de datos
with app.app_context():
    db.create_all()
    create_admin_user()
    add_sample_courts()
    print('Base de datos inicializada correctamente')
