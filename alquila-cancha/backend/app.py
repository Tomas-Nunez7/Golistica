from flask import Flask, render_template, jsonify, redirect, url_for, session, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import os
import threading
import time
import logging
import json
from sqlalchemy import text, exc
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from sqlalchemy import or_, and_
import multiprocessing
import concurrent.futures
from multiprocessing import Process, Queue, Manager
import queue
import signal
import sys

# Inicializar aplicación Flask
app = Flask(__name__, 
    template_folder='../frontend/templates',
    static_folder='../frontend/static')
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///alquila_cancha.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializar SocketIO para comunicación en tiempo real
socketio = SocketIO(app, cors_allowed_origins="*")

# Configurar sistema de auditoría y logging
try:
    # Crear directorio de logs si no existe
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    if not app.debug:
        # Configurar logging para auditoría
        audit_handler = RotatingFileHandler('logs/audit.log', maxBytes=10240000, backupCount=10)
        audit_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        audit_handler.setLevel(logging.INFO)
        app.logger.addHandler(audit_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('Golistica startup')
    
    # Configurar logging para eventos críticos
    critical_handler = RotatingFileHandler('logs/critical.log', maxBytes=10240000, backupCount=10)
    critical_handler.setFormatter(logging.Formatter(
        '%(asctime)s CRITICAL: %(message)s'
    ))
    critical_handler.setLevel(logging.CRITICAL)
    
    critical_logger = logging.getLogger('critical')
    critical_logger.addHandler(critical_handler)
    critical_logger.setLevel(logging.CRITICAL)
    
except Exception as e:
    print(f"Error configurando logs: {e}")
    # Continuar sin logs si hay error

# Inicializar base de datos
db = SQLAlchemy(app)

# Sistema de gestión de procesos y hilos concurrentes
class ProcessManager:
    """Gestiona procesos para tareas de larga duración y CPU intensivas"""
    
    def __init__(self):
        self.processes = {}
        self.task_queue = multiprocessing.Queue()
        self.result_queue = multiprocessing.Queue()
        self.manager = Manager()
        self.shared_state = self.manager.dict()
        self.executor = concurrent.futures.ProcessPoolExecutor(max_workers=multiprocessing.cpu_count())
        
    def start_background_task(self, task_func, task_id, *args, **kwargs):
        """Inicia una tarea en un proceso separado"""
        if task_id in self.processes:
            return False, "Task already running"
            
        try:
            future = self.executor.submit(task_func, *args, **kwargs)
            self.processes[task_id] = {
                'future': future,
                'start_time': datetime.utcnow(),
                'status': 'running'
            }
            return True, "Task started"
        except Exception as e:
            return False, str(e)
    
    def get_task_status(self, task_id):
        """Obtiene el estado de una tarea"""
        if task_id not in self.processes:
            return None
            
        task_info = self.processes[task_id]
        future = task_info['future']
        
        if future.done():
            try:
                result = future.result()
                task_info['status'] = 'completed'
                task_info['result'] = result
                return task_info
            except Exception as e:
                task_info['status'] = 'failed'
                task_info['error'] = str(e)
                return task_info
        elif future.running():
            task_info['status'] = 'running'
            return task_info
        else:
            task_info['status'] = 'pending'
            return task_info
    
    def cancel_task(self, task_id):
        """Cancela una tarea si está en ejecución"""
        if task_id in self.processes:
            future = self.processes[task_id]['future']
            cancelled = future.cancel()
            if cancelled:
                del self.processes[task_id]
                return True
        return False
    
    def cleanup_completed_tasks(self):
        """Limpia tareas completadas"""
        completed_tasks = []
        for task_id, task_info in self.processes.items():
            if task_info['future'].done():
                completed_tasks.append(task_id)
        
        for task_id in completed_tasks:
            del self.processes[task_id]

class ThreadPoolManager:
    """Gestiona pool de hilos para tareas I/O bound"""
    
    def __init__(self, max_workers=10):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.active_tasks = {}
        self.task_counter = 0
        
    def submit_task(self, task_func, *args, **kwargs):
        """Envía una tarea al pool de hilos"""
        self.task_counter += 1
        task_id = f"task_{self.task_counter}"
        
        try:
            future = self.executor.submit(task_func, *args, **kwargs)
            self.active_tasks[task_id] = {
                'future': future,
                'start_time': datetime.utcnow(),
                'status': 'running'
            }
            return task_id, "Task submitted successfully"
        except Exception as e:
            return None, str(e)
    
    def get_task_result(self, task_id, timeout=None):
        """Obtiene el resultado de una tarea"""
        if task_id not in self.active_tasks:
            return None, "Task not found"
            
        future = self.active_tasks[task_id]['future']
        
        try:
            result = future.result(timeout=timeout)
            self.active_tasks[task_id]['status'] = 'completed'
            self.active_tasks[task_id]['result'] = result
            return result, "Task completed"
        except concurrent.futures.TimeoutError:
            return None, "Task timeout"
        except Exception as e:
            self.active_tasks[task_id]['status'] = 'failed'
            self.active_tasks[task_id]['error'] = str(e)
            return None, str(e)
    
    def get_all_active_tasks(self):
        """Obtiene todas las tareas activas"""
        return self.active_tasks
    
    def cleanup_completed_tasks(self):
        """Limpia tareas completadas"""
        completed_tasks = []
        for task_id, task_info in self.active_tasks.items():
            if task_info['future'].done():
                completed_tasks.append(task_id)
        
        for task_id in completed_tasks:
            del self.active_tasks[task_id]

# Variables globales para gestores de concurrencia
process_manager = None
thread_pool = None
resource_monitor = None

# Sistema de monitoreo de recursos
class ResourceMonitor:
    """Monitorea el uso de recursos del sistema"""
    
    def __init__(self):
        self.monitoring = False
        self.monitor_thread = None
        self.stats = {
            'cpu_usage': 0,
            'memory_usage': 0,
            'active_threads': 0,
            'active_processes': 0,
            'timestamp': None
        }
    
    def start_monitoring(self, interval=5):
        """Inicia el monitoreo de recursos"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, args=(interval,))
            self.monitor_thread.daemon = True
            self.monitor_thread.start()
    
    def stop_monitoring(self):
        """Detiene el monitoreo de recursos"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)
    
    def _monitor_loop(self, interval):
        """Bucle de monitoreo"""
        try:
            import psutil
            while self.monitoring:
                self.stats.update({
                    'cpu_usage': psutil.cpu_percent(),
                    'memory_usage': psutil.virtual_memory().percent,
                    'active_threads': threading.active_count(),
                    'active_processes': len(psutil.pids()),
                    'timestamp': datetime.utcnow()
                })
                time.sleep(interval)
        except ImportError:
            # psutil no disponible, monitoreo básico
            while self.monitoring:
                self.stats.update({
                    'cpu_usage': 0,
                    'memory_usage': 0,
                    'active_threads': threading.active_count(),
                    'active_processes': len(process_manager.processes) if process_manager else 0,
                    'timestamp': datetime.utcnow()
                })
                time.sleep(interval)
    
    def get_stats(self):
        """Obtiene estadísticas actuales"""
        return self.stats.copy()

# Tareas de larga duración que se ejecutarán en procesos separados
def data_integrity_check_task():
    """Tarea de verificación de integridad de datos"""
    try:
        # Simular trabajo intensivo de verificación
        time.sleep(2)
        
        results = {
            'check_type': 'data_integrity',
            'timestamp': datetime.utcnow().isoformat(),
            'issues_found': 0,
            'tables_checked': ['user', 'court', 'booking', 'audit_log'],
            'status': 'completed'
        }
        
        # Aquí iría la lógica real de verificación
        # Por ahora simulamos que no hay problemas
        
        return results
    except Exception as e:
        return {
            'check_type': 'data_integrity',
            'timestamp': datetime.utcnow().isoformat(),
            'status': 'failed',
            'error': str(e)
        }

def statistics_calculation_task():
    """Tarea de cálculo de estadísticas"""
    try:
        # Simular cálculo intensivo
        time.sleep(1)
        
        results = {
            'check_type': 'statistics',
            'timestamp': datetime.utcnow().isoformat(),
            'total_users': 0,
            'total_courts': 0,
            'total_bookings': 0,
            'revenue_today': 0,
            'status': 'completed'
        }
        
        # Aquí iría la lógica real de cálculo de estadísticas
        
        return results
    except Exception as e:
        return {
            'check_type': 'statistics',
            'timestamp': datetime.utcnow().isoformat(),
            'status': 'failed',
            'error': str(e)
        }

# Manejo de señales para limpieza graceful
def signal_handler(signum, frame):
    """Manejador de señales para cierre graceful"""
    print(f"Recibida señal {signum}, cerrando procesos...")
    
    # Detener monitoreo
    resource_monitor.stop_monitoring()
    
    # Cancelar todas las tareas activas
    for task_id in list(process_manager.processes.keys()):
        process_manager.cancel_task(task_id)
    
    # Cerrar executors
    process_manager.executor.shutdown(wait=True)
    thread_pool.executor.shutdown(wait=True)
    
    sys.exit(0)

# Registrar manejadores de señales
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

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
    
    # Relaciones
    user = db.relationship('User', backref='bookings')
    court = db.relationship('Court', backref='bookings')

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
        
        with transaction_scope():
            # Verificar si la cancha existe
            court = db.session.query(Court).filter_by(id=court_id).first()
            if not court:
                return jsonify({'success': False, 'message': 'Cancha no encontrada'}), 404
            
            # Verificar si ya existe una reserva en el mismo horario
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
            
            # Crear la reserva
            booking = Booking(
                court_id=court_id,
                user_id=user_id,
                user_name=user_name,
                user_email=user_email,
                booking_date=booking_date,
                start_time=start_time,
                end_time=end_time,
                status='pending'
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
                'booking_id': booking.id
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
    return render_template('profile.html', user=user)

# Endpoints REST API
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

@app.route('/api/bookings', methods=['GET'])
@login_required
def get_bookings():
    user = User.query.get(session['user_id'])
    
    if user.is_admin():
        bookings = Booking.query.all()
    elif user.is_operator():
        bookings = Booking.query.all()
    else:
        bookings = Booking.query.filter_by(user_id=user.id).all()
    
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

if __name__ == '__main__':
    # Configurar multiprocessing para Windows
    multiprocessing.freeze_support()
    
    # Inicializar gestores de concurrencia
    process_manager = ProcessManager()
    thread_pool = ThreadPoolManager()
    resource_monitor = ResourceMonitor()
    
    # Iniciar monitoreo de recursos
    resource_monitor.start_monitoring()
    
    # Iniciar el servidor
    socketio.run(app, debug=True, host='0.0.0.0', port=5002)
