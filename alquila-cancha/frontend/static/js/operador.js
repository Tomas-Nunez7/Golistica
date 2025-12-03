// Sistema de operador
// Socket.IO deshabilitado para evitar conflictos
// const socket = io();

// Variables globales
let currentUser = null;
let bookingsData = [];
let courtsData = [];

// Eventos de SocketIO comentados para evitar errores
/*
socket.on('connect', () => {
    console.log('Operador conectado');
    loadDashboardData();
});

socket.on('new_booking', (data) => {
    showNotification(`Nueva reserva recibida: ${data.user_name}`, 'success');
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
*/

// Sistema de notificaciones
function showNotification(message, type = 'info') {
    const notificationArea = document.getElementById('notification-area');
    const notification = document.createElement('div');
    notification.className = 'notification';
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
        loadBookings(),
        loadCourts(),
        updateStats()
    ]);
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

// Cargar canchas
async function loadCourts() {
    try {
        const response = await fetch('/api/courts');
        courtsData = await response.json();
        updateCourtsGrid();
    } catch (error) {
        console.error('Error al cargar canchas:', error);
    }
}

// Actualizar estadísticas
function updateStats() {
    const today = new Date().toISOString().split('T')[0];
    const todayBookings = bookingsData.filter(b => b.date === today);
    const pendingBookings = bookingsData.filter(b => b.status === 'pending');
    
    document.getElementById('today-bookings').textContent = todayBookings.length;
    document.getElementById('pending-bookings').textContent = pendingBookings.length;
    document.getElementById('my-courts').textContent = courtsData.length;
    
    // Calcular ingresos semanales (simulado)
    const weeklyRevenue = bookingsData
        .filter(b => b.status === 'confirmed')
        .reduce((total, booking) => {
            const court = courtsData.find(c => c.id === booking.court_id);
            return total + (court ? court.price : 0);
        }, 0);
    
    document.getElementById('weekly-revenue').textContent = `$${weeklyRevenue}`;
}

// Actualizar tabla de reservas
function updateBookingsTable() {
    const tbody = document.querySelector('#bookings-table tbody');
    if (!tbody) return;
    
    tbody.innerHTML = bookingsData.map(booking => `
        <tr>
            <td>${booking.id}</td>
            <td>${booking.user_name}</td>
            <td>${booking.court_name}</td>
            <td>${booking.date}</td>
            <td>${booking.start_time} - ${booking.end_time}</td>
            <td>
                <span class="status-badge status-${booking.status}">${booking.status}</span>
            </td>
            <td>
                ${booking.status === 'pending' ? `
                    <button class="btn-action btn-confirm" onclick="confirmBooking(${booking.id})">
                        <i class="fas fa-check"></i>
                    </button>
                    <button class="btn-action btn-cancel" onclick="cancelBooking(${booking.id})">
                        <i class="fas fa-times"></i>
                    </button>
                ` : ''}
            </td>
        </tr>
    `).join('');
}

// Actualizar grid de canchas
function updateCourtsGrid() {
    const courtGrid = document.querySelector('.court-grid');
    if (!courtGrid) return;
    
    courtGrid.innerHTML = courtsData.map(court => `
        <div class="court-card">
            <div class="court-image" style="background-image: url('${court.image}')"></div>
            <div class="court-info">
                <h4>${court.name}</h4>
                <p><i class="fas fa-map-marker-alt"></i> ${court.location}</p>
                <p><i class="fas fa-tag"></i> ${court.type}</p>
                <p><i class="fas fa-dollar-sign"></i> ${court.price}/hora</p>
                <p><i class="fas fa-star"></i> ${court.rating}</p>
                <div style="margin-top: 15px;">
                    <button class="btn btn-primary btn-sm" onclick="viewCourtSchedule(${court.id})">
                        <i class="fas fa-calendar"></i> Ver Horario
                    </button>
                </div>
            </div>
        </div>
    `).join('');
}

// Confirmar reserva
async function confirmBooking(bookingId) {
    try {
        const response = await fetch(`/api/bookings/${bookingId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ status: 'confirmed' })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification('Reserva confirmada correctamente', 'success');
        } else {
            showNotification('Error al confirmar reserva', 'error');
        }
    } catch (error) {
        console.error('Error al confirmar reserva:', error);
        showNotification('Error al confirmar reserva', 'error');
    }
}

// Cancelar reserva
async function cancelBooking(bookingId) {
    if (confirm('¿Estás seguro de cancelar esta reserva?')) {
        try {
            const response = await fetch(`/api/bookings/${bookingId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ status: 'cancelled' })
            });
            
            const result = await response.json();
            
            if (result.success) {
                showNotification('Reserva cancelada correctamente', 'success');
            } else {
                showNotification('Error al cancelar reserva', 'error');
            }
        } catch (error) {
            console.error('Error al cancelar reserva:', error);
            showNotification('Error al cancelar reserva', 'error');
        }
    }
}

// Ver horario de cancha
function viewCourtSchedule(courtId) {
    const court = courtsData.find(c => c.id === courtId);
    if (!court) return;
    
    // Implementar modal con horario de la cancha
    showNotification(`Ver horario de: ${court.name}`, 'info');
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
        rating: parseFloat(formData.get('rating')) || null,
        image: formData.get('image') || null,
        description: formData.get('description')
    };
    
    try {
        const response = await fetch('/api/courts', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(courtData)
        });
        
        if (response.ok) {
            showNotification('Cancha agregada correctamente', 'success');
            closeModal();
            loadCourts();
        } else {
            showNotification('Error al agregar cancha', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showNotification('Error al agregar cancha', 'error');
    }
}

// Navegación del dashboard
document.addEventListener('DOMContentLoaded', () => {
    console.log('Operador JS - DOM cargado');
    
    try {
        setupOperatorNavigation();
        console.log('Operador JS - Navegación configurada');
    } catch (error) {
        console.error('Error en configuración del operador:', error);
    }
});

function setupOperatorNavigation() {
    console.log('Operador JS - Configurando navegación');
    
    const sidebarLinks = document.querySelectorAll('.sidebar-menu a');
    console.log('Operador JS - Links encontrados:', sidebarLinks.length);
    
    if (sidebarLinks.length === 0) {
        console.error('Operador JS - No se encontraron links del menú');
        return;
    }
    
    sidebarLinks.forEach((link, index) => {
        const href = link.getAttribute('href');
        console.log(`Operador JS - Link ${index}:`, href, link.textContent.trim());
        
        // Solo manejar links que empiezan con # (internos del dashboard)
        if (href && href.startsWith('#')) {
            console.log('Operador JS - Manejando link interno:', href);
            
            link.addEventListener('click', (e) => {
                console.log('Operador JS - Click en:', href);
                e.preventDefault();
                
                const targetId = href.substring(1);
                console.log('Operador JS - Target ID:', targetId);
                
                showOperatorSection(targetId);
                
                // Actualizar link activo
                sidebarLinks.forEach(l => l.classList.remove('active'));
                link.classList.add('active');
            });
        } else {
            console.log('Operador JS - Link externo, comportamiento normal:', href);
        }
    });
}

function showOperatorSection(sectionId) {
    console.log('Operador JS - Mostrando sección:', sectionId);
    
    // Ocultar todas las secciones
    const sections = document.querySelectorAll('.content-section');
    console.log('Operador JS - Secciones encontradas:', sections.length);
    sections.forEach(section => {
        section.style.display = 'none';
    });
    
    // Mostrar sección específica
    const targetSection = document.getElementById(sectionId + '-section');
    console.log('Operador JS - Sección objetivo:', targetSection);
    
    if (targetSection) {
        targetSection.style.display = 'block';
        console.log('Operador JS - Sección mostrada');
        
        // Cargar datos específicos de la sección
        switch(sectionId) {
            case 'dashboard':
                loadDashboardData();
                break;
            case 'bookings':
                loadBookings();
                break;
            case 'courts':
                loadCourts();
                break;
            case 'reports':
                // No requiere carga inicial
                break;
        }
    } else {
        console.error('Operador JS - Sección no encontrada:', sectionId + '-section');
    }
}
// Acciones rápidas del operador
function showBookingModal() {
    showNotification('Crear reserva (funcionalidad próximamente)', 'info');
}

function browseCourts() {
    showOperatorSection('courts');
}

function editProfile() {
    showNotification('Editar perfil (funcionalidad próximamente)', 'info');
}

function showHistory() {
    showNotification('Historial completo (funcionalidad próximamente)', 'info');
}

// Cerrar modal
function closeModal() {
    const modal = document.querySelector('.modal');
    if (modal) modal.remove();
}
function filterBookings() {
    const statusFilter = document.getElementById('status-filter').value;
    const dateFilter = document.getElementById('date-filter').value;
    
    let filteredBookings = bookingsData;
    
    if (statusFilter) {
        filteredBookings = filteredBookings.filter(b => b.status === statusFilter);
    }
    
    if (dateFilter) {
        filteredBookings = filteredBookings.filter(b => b.date === dateFilter);
    }
    
    // Actualizar tabla con resultados filtrados
    const tbody = document.querySelector('#bookings-table tbody');
    if (!tbody) return;
    
    tbody.innerHTML = filteredBookings.map(booking => `
        <tr>
            <td>${booking.id}</td>
            <td>${booking.user_name}</td>
            <td>${booking.court_name}</td>
            <td>${booking.date}</td>
            <td>${booking.start_time} - ${booking.end_time}</td>
            <td>
                <span class="status-badge status-${booking.status}">${booking.status}</span>
            </td>
            <td>
                ${booking.status === 'pending' ? `
                    <button class="btn-action btn-confirm" onclick="confirmBooking(${booking.id})">
                        <i class="fas fa-check"></i>
                    </button>
                    <button class="btn-action btn-cancel" onclick="cancelBooking(${booking.id})">
                        <i class="fas fa-times"></i>
                    </button>
                ` : ''}
            </td>
        </tr>
    `).join('');
}

// Generar reporte
function generateReport() {
    const reportType = document.getElementById('report-type').value;
    const reportContent = document.getElementById('report-content');
    
    let reportData = '';
    
    switch(reportType) {
        case 'daily':
            const today = new Date().toISOString().split('T')[0];
            const todayBookings = bookingsData.filter(b => b.date === today);
            reportData = generateDailyReport(todayBookings);
            break;
        case 'weekly':
            reportData = generateWeeklyReport();
            break;
        case 'monthly':
            reportData = generateMonthlyReport();
            break;
    }
    
    reportContent.innerHTML = `
        <div class="report-content">
            <h4>Reporte ${reportType === 'daily' ? 'Diario' : reportType === 'weekly' ? 'Semanal' : 'Mensual'}</h4>
            ${reportData}
        </div>
    `;
}

// Generar reporte diario
function generateDailyReport(bookings) {
    const confirmed = bookings.filter(b => b.status === 'confirmed').length;
    const pending = bookings.filter(b => b.status === 'pending').length;
    const cancelled = bookings.filter(b => b.status === 'cancelled').length;
    
    return `
        <div class="report-stats">
            <div class="stat-item">
                <strong>Reservas Confirmadas:</strong> ${confirmed}
            </div>
            <div class="stat-item">
                <strong>Reservas Pendientes:</strong> ${pending}
            </div>
            <div class="stat-item">
                <strong>Reservas Canceladas:</strong> ${cancelled}
            </div>
            <div class="stat-item">
                <strong>Total:</strong> ${bookings.length}
            </div>
        </div>
    `;
}

// Generar reporte semanal
function generateWeeklyReport() {
    // Implementar lógica de reporte semanal
    return `
        <div class="report-stats">
            <div class="stat-item">
                <strong>Reservas esta semana:</strong> ${bookingsData.length}
            </div>
            <div class="stat-item">
                <strong>Tasa de confirmación:</strong> 85%
            </div>
            <div class="stat-item">
                <strong>Ingresos estimados:</strong> $50,000
            </div>
        </div>
    `;
}

// Generar reporte mensual
function generateMonthlyReport() {
    // Implementar lógica de reporte mensual
    return `
        <div class="report-stats">
            <div class="stat-item">
                <strong>Reservas este mes:</strong> ${bookingsData.length * 4}
            </div>
            <div class="stat-item">
                <strong>Canchas más populares:</strong>
                <ul>
                    <li>Cancha de Fútbol 5 - 45 reservas</li>
                    <li>Cancha de Tenis - 32 reservas</li>
                    <li>Cancha de Básquet - 28 reservas</li>
                </ul>
            </div>
            <div class="stat-item">
                <strong>Ingresos totales:</strong> $200,000
            </div>
        </div>
    `;
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
                document.getElementById('bookings-section').style.display = 'block';
                break;
            case 'bookings':
                document.getElementById('bookings-section').style.display = 'block';
                break;
            case 'courts':
                document.getElementById('courts-section').style.display = 'block';
                break;
            case 'reports':
                document.getElementById('reports-section').style.display = 'block';
                break;
            default:
                document.getElementById('bookings-section').style.display = 'block';
        }
    });
});

// Inicializar al cargar la página
document.addEventListener('DOMContentLoaded', () => {
    loadDashboardData();
});
