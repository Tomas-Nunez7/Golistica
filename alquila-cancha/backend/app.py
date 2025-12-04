import multiprocessing
from config import app, socketio, ProcessManager, ThreadPoolManager, ResourceMonitor

# Importar todos los módulos para registrar las rutas y funcionalidades
import models
import routes  
import utils

if __name__ == '__main__':
    # Configurar multiprocessing para Windows
    multiprocessing.freeze_support()
    
    # Inicializar gestores de concurrencia y asignar a variables globales en utils
    utils.process_manager = ProcessManager()
    utils.thread_pool = ThreadPoolManager()
    utils.resource_monitor = ResourceMonitor()
    
    # Iniciar monitoreo de recursos (desactivado temporalmente)
    # utils.resource_monitor.start_monitoring()
    
    print("Gestores de concurrencia inicializados correctamente")
    
    # Iniciar el servidor
    socketio.run(app, debug=True, host='0.0.0.0', port=5002)
