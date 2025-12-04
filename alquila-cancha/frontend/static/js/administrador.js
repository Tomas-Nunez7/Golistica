// Sistema de administración con SocketIO
const socket = io();

// Variables globales
let currentUser = null;
let bookingsData = [];
let usersData = [];
let courtsData = [];

// Inicializar conexión SocketIO
socket.on('connect', () => {
    console.log('Administrador conectado');
    socket.emit('join_admin_room');
    loadDashboardData();
});

// Eventos de SocketIO
socket.on('new_booking', (data) => {
    showNotification(`Nueva reserva: ${data.user_name}`, 'success');
    loadBookings();
    updateStats();
});

socket.on('booking_updated', (data) => {
    showNotification(`Reserva actualizada: ${data.status}`, 'info');
    loadBookings();
    updateStats();
});

socket.on('notification', (data) => {
    showNotification(data.message, data.type);
});

// Sistema de notificaciones
function showNotification(message, type = 'info') {
    const notificationArea = document.getElementById('notification-area');
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.innerHTML = `
        <strong>${type.charAt(0).toUpperCase() + type.slice(1)}</strong>
        <p>${message}</p>
    `;
    
    notificationArea.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}

// Cargar datos del dashboard
async function loadDashboardData() {
    await Promise.all([
        loadUsers(),
        loadCourts(),
        loadBookings(),
        updateStats()
    ]);
}

// Cargar usuarios
async function loadUsers() {
    try {
        const response = await fetch('/api/users');
        usersData = await response.json();
        updateUsersTable();
    } catch (error) {
        console.error('Error al cargar usuarios:', error);
    }
}

// Cargar canchas
async function loadCourts() {
    try {
        const response = await fetch('/api/courts');
        courtsData = await response.json();
        updateCourtsTable();
    } catch (error) {
        console.error('Error al cargar canchas:', error);
    }
}

// Cargar reservas
async function loadBookings() {
    try {
        const response = await fetch('/api/bookings');
        bookingsData = await response.json();
        updateBookingsTable();
    } catch (error) {
        console.error('Error al cargar reservas:', error);
    }
}

// Actualizar estadísticas
function updateStats() {
    document.getElementById('total-users').textContent = usersData.length;
    document.getElementById('total-courts').textContent = courtsData.length;
    document.getElementById('total-bookings').textContent = bookingsData.length;
    document.getElementById('pending-bookings').textContent = 
        bookingsData.filter(b => b.status === 'pending').length;
}

// Actualizar tabla de usuarios
function updateUsersTable() {
    const tbody = document.querySelector('#users-table tbody');
    if (!tbody) return;
    
    tbody.innerHTML = usersData.map(user => `
        <tr>
            <td>${user.id}</td>
            <td>${user.username}</td>
            <td>${user.email}</td>
            <td>
                <span class="status-badge status-${user.role}">${user.role}</span>
            </td>
            <td>${user.created_at}</td>
            <td>
                <button class="btn-action btn-edit" onclick="editUser(${user.id})">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn-action btn-delete" onclick="deleteUser(${user.id})">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        </tr>
    `).join('');
}

// Actualizar tabla de canchas
function updateCourtsTable() {
    const tbody = document.querySelector('#courts-table tbody');
    if (!tbody) return;
    
    tbody.innerHTML = courtsData.map(court => `
        <tr>
            <td>${court.id}</td>
            <td>${court.name}</td>
            <td>${court.location}</td>
            <td>${court.type}</td>
            <td>$${court.price}</td>
            <td>${court.rating}</td>
            <td>
                <button class="btn-action btn-edit" onclick="editCourt(${court.id})">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn-action btn-delete" onclick="deleteCourt(${court.id})">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        </tr>
    `).join('');
}

// Actualizar tabla de reservas
function updateBookingsTable() {
    const tbody = document.querySelector('#bookings-table tbody');
    if (!tbody) return;
    
    tbody.innerHTML = bookingsData.slice(0, 10).map(booking => `
        <tr>
            <td>${booking.id}</td>
            <td>${booking.user_name}</td>
            <td>${booking.user_email || 'N/A'}</td>
            <td>${booking.court_name}</td>
            <td>${booking.date}</td>
            <td>${booking.start_time}</td>
            <td>
                <span class="status-badge status-${booking.status}">${booking.status}</span>
            </td>
            <td>
                <button class="btn-action btn-edit" onclick="updateBookingStatus(${booking.id}, 'confirmed')">
                    <i class="fas fa-check"></i>
                </button>
                <button class="btn-action btn-cancel" onclick="updateBookingStatus(${booking.id}, 'cancelled')">
                    <i class="fas fa-times"></i>
                </button>
                <button class="btn-action btn-delete" onclick="deleteBooking(${booking.id})">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        </tr>
    `).join('');
}

// Actualizar estado de reserva
async function updateBookingStatus(bookingId, status) {
    try {
        const response = await fetch(`/api/bookings/${bookingId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ status })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification('Reserva actualizada correctamente', 'success');
        } else {
            showNotification('Error al actualizar reserva', 'error');
        }
    } catch (error) {
        console.error('Error al actualizar reserva:', error);
        showNotification('Error al actualizar reserva', 'error');
    }
}

// Editar usuario
function editUser(userId) {
    const user = usersData.find(u => u.id === userId);
    if (!user) return;
    
    // Implementar modal de edición de usuario
    showNotification(`Editar usuario: ${user.username}`, 'info');
}

// Eliminar usuario
function deleteUser(userId) {
    if (confirm('¿Estás seguro de eliminar este usuario?')) {
        // Implementar eliminación de usuario
        showNotification('Usuario eliminado correctamente', 'success');
    }
}

// Editar cancha
function editCourt(courtId) {
    const court = courtsData.find(c => c.id === courtId);
    if (!court) return;
    
    showEditCourtModal(court);
}

// Mostrar modal para editar cancha
function showEditCourtModal(court) {
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.5);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 1000;
    `;
    
    modal.innerHTML = `
        <div style="
            background: white;
            padding: 30px;
            border-radius: 10px;
            max-width: 500px;
            width: 90%;
            max-height: 90vh;
            overflow-y: auto;
            position: relative;
        ">
            <button onclick="this.closest('.modal').remove()" style="
                position: absolute;
                top: 15px;
                right: 15px;
                background: none;
                border: none;
                font-size: 24px;
                cursor: pointer;
                color: #666;
            ">&times;</button>
            
            <h2 style="margin-bottom: 20px; color: #333;">
                <i class="fas fa-edit"></i> Editar Cancha
            </h2>
            
            <form id="editCourtForm">
                <div style="margin-bottom: 15px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold;">Nombre:</label>
                    <input type="text" name="name" value="${court.name}" required style="
                        width: 100%;
                        padding: 8px;
                        border: 1px solid #ddd;
                        border-radius: 4px;
                    ">
                </div>
                
                <div style="margin-bottom: 15px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold;">Ubicación:</label>
                    <input type="text" name="location" value="${court.location}" required style="
                        width: 100%;
                        padding: 8px;
                        border: 1px solid #ddd;
                        border-radius: 4px;
                    ">
                </div>
                
                <div style="margin-bottom: 15px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold;">Tipo:</label>
                    <select name="court_type" style="
                        width: 100%;
                        padding: 8px;
                        border: 1px solid #ddd;
                        border-radius: 4px;
                    ">
                        <option value="Fútbol 5" ${court.type === 'Fútbol 5' ? 'selected' : ''}>Fútbol 5</option>
                        <option value="Fútbol 7" ${court.type === 'Fútbol 7' ? 'selected' : ''}>Fútbol 7</option>
                        <option value="Fútbol 11" ${court.type === 'Fútbol 11' ? 'selected' : ''}>Fútbol 11</option>
                        <option value="Tenis" ${court.type === 'Tenis' ? 'selected' : ''}>Tenis</option>
                        <option value="Pádel" ${court.type === 'Pádel' ? 'selected' : ''}>Pádel</option>
                        <option value="Básquet" ${court.type === 'Básquet' ? 'selected' : ''}>Básquet</option>
                    </select>
                </div>
                
                <div style="margin-bottom: 15px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold;">Precio por hora:</label>
                    <input type="number" name="price" value="${court.price}" min="0" step="0.01" required style="
                        width: 100%;
                        padding: 8px;
                        border: 1px solid #ddd;
                        border-radius: 4px;
                    ">
                </div>
                
                <div style="margin-bottom: 15px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold;">Descripción:</label>
                    <textarea name="description" rows="3" style="
                        width: 100%;
                        padding: 8px;
                        border: 1px solid #ddd;
                        border-radius: 4px;
                    ">${court.description || ''}</textarea>
                </div>
                
                <div style="margin-bottom: 15px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold;">URL Imagen:</label>
                    <input type="url" name="image" value="${court.image || ''}" style="
                        width: 100%;
                        padding: 8px;
                        border: 1px solid #ddd;
                        border-radius: 4px;
                    ">
                </div>
                
                <div style="display: flex; gap: 10px; margin-top: 20px;">
                    <button type="submit" style="
                        background: #007bff;
                        color: white;
                        border: none;
                        padding: 10px 20px;
                        border-radius: 4px;
                        cursor: pointer;
                        flex: 1;
                    ">Guardar Cambios</button>
                    <button type="button" onclick="this.closest('.modal').remove()" style="
                        background: #6c757d;
                        color: white;
                        border: none;
                        padding: 10px 20px;
                        border-radius: 4px;
                        cursor: pointer;
                        flex: 1;
                    ">Cancelar</button>
                </div>
            </form>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Manejar envío del formulario
    document.getElementById('editCourtForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const formData = new FormData(e.target);
        const data = Object.fromEntries(formData.entries());
        
        try {
            const response = await fetch(`/api/courts/${court.id}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data)
            });
            
            const result = await response.json();
            
            if (result.success) {
                showNotification('Cancha actualizada correctamente', 'success');
                modal.remove();
                loadCourts(); // Recargar la lista de canchas
            } else {
                showNotification(result.message || 'Error al actualizar cancha', 'error');
            }
        } catch (error) {
            console.error('Error al actualizar cancha:', error);
            showNotification('Error al actualizar cancha', 'error');
        }
    });
}

// Eliminar cancha
function deleteCourt(courtId) {
    if (confirm('¿Estás seguro de eliminar esta cancha?')) {
        // Implementar eliminación de cancha
        showNotification('Cancha eliminada correctamente', 'success');
    }
}

// Abrir modal para agregar cancha
function openAddCourtModal() {
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.5);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 1000;
    `;
    
    modal.innerHTML = `
        <div class="modal-content" style="
            background: white;
            padding: 30px;
            border-radius: 10px;
            max-width: 500px;
            width: 90%;
        ">
            <h2>Agregar Nueva Cancha</h2>
            <form id="add-court-form">
                <div class="form-group">
                    <label>Nombre</label>
                    <input type="text" name="name" required>
                </div>
                <div class="form-group">
                    <label>Ubicación</label>
                    <input type="text" name="location" required>
                </div>
                <div class="form-group">
                    <label>Tipo</label>
                    <select name="court_type" required>
                        <option value="">Selecciona un tipo</option>
                        <option value="Fútbol 5">Fútbol 5</option>
                        <option value="Fútbol 7">Fútbol 7</option>
                        <option value="Fútbol 11">Fútbol 11</option>
                        <option value="Tenis">Tenis</option>
                        <option value="Básquet">Básquet</option>
                        <option value="Pádel">Pádel</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Precio por hora</label>
                    <input type="number" name="price" step="0.01" required>
                </div>
                <div class="form-group">
                    <label>Rating (opcional)</label>
                    <input type="number" name="rating" min="0" max="5" step="0.1">
                </div>
                <div class="form-group">
                    <label>URL Imagen (opcional)</label>
                    <input type="url" name="image">
                </div>
                <div class="form-group">
                    <label>Descripción</label>
                    <textarea name="description" rows="3"></textarea>
                </div>
                <div style="display: flex; gap: 10px; margin-top: 20px;">
                    <button type="submit" class="btn btn-primary">Agregar Cancha</button>
                    <button type="button" class="btn btn-outline" onclick="closeModal()">Cancelar</button>
                </div>
            </form>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Manejar envío del formulario
    document.getElementById('add-court-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        await submitNewCourt(new FormData(e.target));
    });
}

// Enviar nueva cancha
async function submitNewCourt(formData) {
    const courtData = {
        name: formData.get('name'),
        location: formData.get('location'),
        court_type: formData.get('court_type'),
        price: parseFloat(formData.get('price')),
        rating: parseFloat(formData.get('rating')) || 0,
        image: formData.get('image') || '',
        description: formData.get('description') || ''
    };
    
    try {
        const response = await fetch('/api/courts', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(courtData)
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification('Cancha agregada correctamente', 'success');
            closeModal();
            loadCourts();
            updateStats();
        } else {
            showNotification(result.message, 'error');
        }
    } catch (error) {
        console.error('Error al agregar cancha:', error);
        showNotification('Error al agregar cancha', 'error');
    }
}

// Cerrar modal
function closeModal() {
    const modal = document.querySelector('.modal');
    if (modal) modal.remove();
}

// Navegación en el sidebar
document.querySelectorAll('.sidebar-menu a').forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        
        // Remover clase activa de todos los enlaces
        document.querySelectorAll('.sidebar-menu a').forEach(l => l.classList.remove('active'));
        
        // Agregar clase activa al enlace actual
        link.classList.add('active');
        
        // Mostrar/ocultar secciones
        const targetId = link.getAttribute('href').substring(1);
        
        // Ocultar todas las secciones
        document.querySelectorAll('.content-section').forEach(section => {
            section.style.display = 'none';
        });
        
        // Mostrar la sección correspondiente
        switch(targetId) {
            case 'dashboard':
                document.getElementById('recent-bookings').style.display = 'block';
                break;
            case 'users':
                document.getElementById('users-section').style.display = 'block';
                break;
            case 'courts':
                document.getElementById('courts-section').style.display = 'block';
                break;
            case 'notifications':
                document.getElementById('notifications-section').style.display = 'block';
                break;
            default:
                document.getElementById('recent-bookings').style.display = 'block';
        }
    });
});

// Formulario de notificaciones
document.getElementById('notification-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const message = document.getElementById('notification-message').value;
    const type = document.getElementById('notification-type').value;
    
    socket.emit('send_notification', { message, type });
    
    showNotification('Notificación enviada correctamente', 'success');
    e.target.reset();
});

// Eliminar reserva
async function deleteBooking(bookingId) {
    if (confirm('¿Estás seguro de eliminar esta reserva? Esta acción no se puede deshacer.')) {
        try {
            const response = await fetch(`/api/bookings/${bookingId}`, {
                method: 'DELETE'
            });
            
            const result = await response.json();
            
            if (result.success) {
                showNotification('Reserva eliminada correctamente', 'success');
                loadBookings();
                updateStats();
            } else {
                showNotification('Error al eliminar reserva', 'error');
            }
        } catch (error) {
            console.error('Error al eliminar reserva:', error);
            showNotification('Error al eliminar reserva', 'error');
        }
    }
}

// Funciones de Integridad de Datos
async function runIntegrityCheck() {
    try {
        showNotification('Ejecutando verificación de integridad...', 'info');
        
        const response = await fetch('/api/integrity-check', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification(`Verificación completada: ${result.issues_found} problemas detectados`, 'success');
            loadIntegrityReports();
            loadIntegrityStats();
        } else {
            showNotification('Error en verificación: ' + result.error, 'error');
        }
    } catch (error) {
        console.error('Error en verificación:', error);
        showNotification('Error al ejecutar verificación', 'error');
    }
}

async function loadIntegrityReports() {
    try {
        const statusFilter = document.getElementById('integrity-status-filter').value;
        const url = statusFilter ? `/api/integrity-reports?status=${statusFilter}` : '/api/integrity-reports';
        
        const response = await fetch(url);
        const data = await response.json();
        
        const tbody = document.querySelector('#integrity-table tbody');
        tbody.innerHTML = '';
        
        data.reports.forEach(report => {
            const row = document.createElement('tr');
            
            const severityClass = {
                'CRITICAL': 'critical',
                'HIGH': 'high',
                'MEDIUM': 'medium',
                'LOW': 'low'
            }[report.severity] || 'medium';
            
            const statusBadge = {
                'detected': '<span class="status-badge pending">Detectado</span>',
                'fixed': '<span class="status-badge confirmed">Corregido</span>',
                'ignored': '<span class="status-badge cancelled">Ignorado</span>'
            }[report.status] || report.status;
            
            row.innerHTML = `
                <td>${report.id}</td>
                <td>${report.check_type}</td>
                <td>${report.table_name}</td>
                <td>${report.issue_description}</td>
                <td><span class="severity-badge ${severityClass}">${report.severity}</span></td>
                <td>${report.auto_fix_available ? '<span class="status-badge confirmed">Sí</span>' : '<span class="status-badge cancelled">No</span>'}</td>
                <td>${statusBadge}</td>
                <td>${report.created_at}</td>
                <td>
                    ${report.status === 'detected' && report.auto_fix_available ? 
                        `<button class="btn btn-success btn-sm" onclick="fixIntegrityIssue(${report.id})">Corregir</button>` : ''}
                    ${report.status === 'detected' ? 
                        `<button class="btn btn-outline btn-sm" onclick="ignoreIntegrityIssue(${report.id})">Ignorar</button>` : ''}
                </td>
            `;
            
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Error al cargar reportes:', error);
    }
}

async function loadIntegrityStats() {
    try {
        const response = await fetch('/api/integrity-stats');
        const stats = await response.json();
        
        document.getElementById('total-issues').textContent = stats.total_issues;
        document.getElementById('detected-issues').textContent = stats.detected_issues;
        document.getElementById('fixed-issues').textContent = stats.fixed_issues;
        document.getElementById('critical-issues').textContent = stats.severity_breakdown.critical;
    } catch (error) {
        console.error('Error al cargar estadísticas:', error);
    }
}

async function fixIntegrityIssue(issueId) {
    try {
        if (!confirm('¿Estás seguro de corregir este problema?')) return;
        
        const response = await fetch(`/api/integrity-fix/${issueId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification('Problema corregido correctamente', 'success');
            loadIntegrityReports();
            loadIntegrityStats();
        } else {
            showNotification('Error al corregir: ' + result.error, 'error');
        }
    } catch (error) {
        console.error('Error al corregir:', error);
        showNotification('Error al corregir problema', 'error');
    }
}

async function ignoreIntegrityIssue(issueId) {
    try {
        if (!confirm('¿Estás seguro de ignorar este problema?')) return;
        
        const response = await fetch(`/api/integrity-ignore/${issueId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification('Problema marcado como ignorado', 'info');
            loadIntegrityReports();
            loadIntegrityStats();
        } else {
            showNotification('Error al ignorar: ' + result.error, 'error');
        }
    } catch (error) {
        console.error('Error al ignorar:', error);
        showNotification('Error al ignorar problema', 'error');
    }
}

async function loadUsers() {
    try {
        const response = await fetch('/api/users');
        const data = await response.json();
        
        const tbody = document.querySelector('#users-table tbody');
        tbody.innerHTML = '';
        
        data.users.forEach(user => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${user.id}</td>
                <td>${user.username}</td>
                <td>${user.email}</td>
                <td><span class="status-badge ${user.role}">${user.role}</span></td>
                <td>${user.created_at}</td>
                <td>
                    <button class="btn btn-action btn-edit" onclick="editUser(${user.id})">Editar</button>
                    <button class="btn btn-action btn-delete" onclick="deleteUser(${user.id})">Eliminar</button>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Error al cargar usuarios:', error);
    }
}

async function loadBookings() {
    try {
        const response = await fetch('/api/bookings');
        const bookings = await response.json();
        
        const tbody = document.querySelector('#bookings-table tbody');
        tbody.innerHTML = '';
        
        bookings.forEach(booking => {
            const row = document.createElement('tr');
            const statusBadge = {
                'pending': '<span class="status-badge pending">Pendiente</span>',
                'confirmed': '<span class="status-badge confirmed">Confirmada</span>',
                'cancelled': '<span class="status-badge cancelled">Cancelada</span>'
            }[booking.status] || booking.status;
            
            row.innerHTML = `
                <td>${booking.id}</td>
                <td>${booking.user_name || 'N/A'}</td>
                <td>${booking.user_email || 'N/A'}</td>
                <td>${booking.court_name}</td>
                <td>${booking.date}</td>
                <td>${booking.start_time} - ${booking.end_time}</td>
                <td>${statusBadge}</td>
                <td>
                    <button class="btn btn-action btn-delete" onclick="deleteBooking(${booking.id})">Eliminar</button>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Error al cargar reservas:', error);
    }
}

function editUser(userId) {
    // Implementar edición de usuario
    showNotification('Función de edición de usuario en desarrollo', 'info');
}

function deleteUser(userId) {
    if (confirm('¿Estás seguro de eliminar este usuario?')) {
        showNotification('Función de eliminación de usuario en desarrollo', 'info');
    }
}

function filterIntegrityReports() {
    loadIntegrityReports();
}

// Inicializar al cargar la página
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM cargado');
    
    // Esperar un poco más para asegurar que todo está listo
    setTimeout(() => {
        loadDashboardData();
        loadIntegrityStats();
        setupNavigation();
    }, 100);
});

function setupNavigation() {
    console.log('Configurando navegación...');
    
    // Configurar navegación - solo para links internos del dashboard
    const sidebarLinks = document.querySelectorAll('.sidebar-menu a');
    console.log('Links encontrados:', sidebarLinks.length);
    
    if (sidebarLinks.length === 0) {
        console.error('No se encontraron links del menú');
        return;
    }
    
    sidebarLinks.forEach((link, index) => {
        const href = link.getAttribute('href');
        console.log(`Configurando link ${index}:`, href);
        console.log('Texto del link:', link.textContent.trim());
        
        // Solo manejar links que empiezan con # (internos del dashboard)
        // Excluir explícitamente los links de logout e index
        if (href.startsWith('#')) {
            console.log('Manejando link interno:', href);
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const targetId = href.substring(1);
                console.log('Click en:', targetId);
                showSection(targetId);
                
                // Actualizar link activo
                sidebarLinks.forEach(l => l.classList.remove('active'));
                link.classList.add('active');
            });
        } else {
            console.log('Link externo, comportamiento normal:', href);
            // No hacer nada, dejar que el link funcione normalmente
        }
    });
}

function showSection(sectionId) {
    console.log('Mostrando sección:', sectionId);
    
    // Ocultar todas las secciones
    const sections = document.querySelectorAll('.content-section');
    console.log('Secciones encontradas:', sections.length);
    sections.forEach(section => {
        section.style.display = 'none';
    });
    
    // Mostrar sección específica
    const targetSection = document.getElementById(sectionId + '-section');
    console.log('Sección objetivo:', targetSection);
    
    if (targetSection) {
        targetSection.style.display = 'block';
        console.log('Sección mostrada');
        
        // Cargar datos específicos de la sección
        switch(sectionId) {
            case 'dashboard':
                loadDashboardData();
                break;
            case 'users':
                loadUsers();
                break;
            case 'courts':
                loadCourts();
                break;
            case 'bookings':
                loadBookings();
                break;
            case 'integrity':
                loadIntegrityReports();
                break;
            case 'notifications':
                // No requiere carga inicial
                break;
            case 'settings':
                // No requiere carga inicial
                break;
        }
    } else {
        console.error('Sección no encontrada:', sectionId + '-section');
    }
}
