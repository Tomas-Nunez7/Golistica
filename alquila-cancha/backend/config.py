from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
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
