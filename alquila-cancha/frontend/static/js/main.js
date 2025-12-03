                                        // Sistema de comunicación en tiempo real con SocketIO
// Solo inicializar si no estamos en páginas de autenticación
if (!window.location.pathname.includes('/login') && 
    !window.location.pathname.includes('/register')) {
    
    const socket = io();
    
    // Variables globales
    let courtsData = [];
    let currentUser = null;
    
    // Elementos del DOM
    const courtGrid = document.querySelector('.court-grid');
    
    // Inicializar conexión SocketIO
    socket.on('connect', () => {
        console.log('Conectado al servidor');
        checkUserRole();
    });
    
    socket.on('disconnect', () => {
        console.log('Desconectado del servidor');
    });
    
    socket.on('notification', (data) => {
        showNotification(data.message, data.type);
    });
    
    // Función para verificar rol de usuario
    function checkUserRole() {
        fetch('/api/current-user')
            .then(response => response.json())
            .then(data => {
                if (data.user) {
                    currentUser = data.user;
                }
            })
            .catch(error => console.error('Error al obtener usuario:', error));
    }

    // Sistema de notificaciones
    function showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `alert alert-${type}`;
        notification.textContent = message;
        
        const container = document.querySelector('.flash-messages') || createFlashContainer();
        container.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 5000);
    }
    
    function createFlashContainer() {
        const container = document.createElement('div');
        container.className = 'flash-messages';
        container.style.cssText = `
            position: fixed;
            top: 80px;
            right: 20px;
            z-index: 1001;
            max-width: 300px;
        `;
        document.body.appendChild(container);
        return container;
    }

    // Sistema de manejo de concurrencia en el frontend
    class ConcurrentRequestManager {
        constructor() {
            this.pendingRequests = new Map();
            this.requestQueue = [];
            this.maxConcurrent = 5;
            this.activeRequests = 0;
        }
        
        async executeRequest(key, requestFn) {
            if (this.pendingRequests.has(key)) {
                return await this.pendingRequests.get(key);
            }
            
            if (this.activeRequests >= this.maxConcurrent) {
                return new Promise((resolve, reject) => {
                    this.requestQueue.push({ key, requestFn, resolve, reject });
                });
            }
            
            this.activeRequests++;
            const promise = this._executeRequest(requestFn);
            this.pendingRequests.set(key, promise);
            
            try {
                const result = await promise;
                return result;
            } finally {
                this.pendingRequests.delete(key);
                this.activeRequests--;
                this._processQueue();
            }
        }
        
        async _executeRequest(requestFn) {
            try {
                return await requestFn();
            } catch (error) {
                console.error('Error en petición concurrente:', error);
                throw error;
            }
        }
        
        _processQueue() {
            if (this.requestQueue.length > 0 && this.activeRequests < this.maxConcurrent) {
                const { key, requestFn, resolve, reject } = this.requestQueue.shift();
                this.executeRequest(key, requestFn)
                    .then(resolve)
                    .catch(reject);
            }
        }
    }
    
    const requestManager = new ConcurrentRequestManager();
    
    // Función para buscar canchas con manejo de concurrencia
    async function searchCourts() {
        const courtType = document.getElementById('court-type').value;
        const date = document.getElementById('search-date').value;
        const time = document.getElementById('search-time').value;
        
        showLoadingIndicator(true);
        
        let searchUrl = '/search?';
        const params = [];
        
        if (courtType) {
            const typeMap = {
                'futbol-5': 'Fútbol 5',
                'futbol-7': 'Fútbol 7', 
                'futbol-11': 'Fútbol 11'
            };
            params.push(`type=${encodeURIComponent(typeMap[courtType])}`);
        }
        
        if (date) params.push(`date=${encodeURIComponent(date)}`);
        if (time) params.push(`time=${encodeURIComponent(time)}`);
        
        searchUrl += params.join('&');
        
        const requestKey = `search_${courtType}_${date}_${time}`;
        
        try {
            const courts = await requestManager.executeRequest(requestKey, async () => {
                const response = await fetch(searchUrl);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return await response.json();
            });
            
            updateCourtGrid(courts);
            document.getElementById('canchas').scrollIntoView({ behavior: 'smooth' });
            
        } catch (error) {
            console.error('Error al buscar canchas:', error);
            showNotification('Error al buscar canchas: ' + error.message, 'error');
        } finally {
            showLoadingIndicator(false);
        }
    }
    
    // Función para actualizar la cuadrícula de canchas
    function updateCourtGrid(courts) {
        const gridContainer = document.querySelector('.court-grid');
        
        if (courts.length === 0) {
            gridContainer.innerHTML = '<p style="text-align: center; padding: 40px;">No se encontraron canchas con esos criterios.</p>';
            return;
        }
        
        gridContainer.innerHTML = courts.map(court => `
            <div class="court-card">
                <div class="court-image" style="background-image: url('${court.image}')">
                    <div class="court-type-badge">${court.court_type}</div>
                </div>
                <div class="court-info">
                    <h4>${court.name}</h4>
                    <p><i class="fas fa-map-marker-alt"></i> ${court.location}</p>
                    <p><i class="fas fa-dollar-sign"></i> $${court.price}/hora</p>
                    <p><i class="fas fa-star"></i> ${court.rating || 'N/A'}</p>
                    <button class="btn btn-primary" onclick="bookCourt(${court.id})">
                        Reservar
                    </button>
                </div>
            </div>
        `).join('');
    }
    
    // Función para mostrar indicador de carga
    function showLoadingIndicator(show) {
        let indicator = document.getElementById('loading-indicator');
        
        if (show) {
            if (!indicator) {
                indicator = document.createElement('div');
                indicator.id = 'loading-indicator';
                indicator.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Buscando...';
                indicator.style.cssText = `
                    position: fixed;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                    background: rgba(0,0,0,0.8);
                    color: white;
                    padding: 20px;
                    border-radius: 8px;
                    z-index: 9999;
                `;
                document.body.appendChild(indicator);
            }
        } else {
            if (indicator) {
                indicator.remove();
            }
        }
    }
    
    // Cargar canchas al iniciar
    document.addEventListener('DOMContentLoaded', () => {
        loadCourts();
    });
    
    function loadCourts() {
        fetch('/api/courts')
            .then(response => response.json())
            .then(courts => {
                courtsData = courts;
                updateCourtGrid(courts);
            })
            .catch(error => {
                console.error('Error al cargar canchas:', error);
                showNotification('Error al cargar canchas', 'error');
            });
    }
    
    // Función para reservar cancha
    function bookCourt(courtId) {
        const court = courtsData.find(c => c.id === courtId);
        if (!court) return;
        
        showNotification(`Función de reserva para ${court.name} - En desarrollo`, 'info');
    }

} // Fin del condicional de páginas de autenticación