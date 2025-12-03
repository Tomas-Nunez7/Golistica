// Sistema de usuario con SocketIO
// Solo inicializar si estamos en la página de usuario
if (window.location.pathname.includes('/user') || 
    window.location.pathname.includes('/profile') ||
    document.getElementById('user-dashboard')) {
    
    const socket = io();
    
    // Variables globales
    let currentUser = null;
    let bookingsData = [];
    let courtsData = [];
    
    // Inicializar conexión SocketIO
    socket.on('connect', () => {
        console.log('Usuario conectado');
        loadUserData();
    });
    
    // Eventos de SocketIO
    socket.on('booking_updated', (data) => {
        showNotification(`Tu reserva ha sido ${data.status}`, 'info');
        loadBookings();
    });
    
    socket.on('notification', (data) => {
        showNotification(data.message, data.type);
    });

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

    // Cargar datos del usuario
    async function loadUserData() {
        await Promise.all([
            loadCurrentUser(),
            loadBookings(),
            loadRecommendedCourts()
        ]);
    }

    // Cargar información del usuario actual
    async function loadCurrentUser() {
        try {
            const response = await fetch('/api/current-user');
            const data = await response.json();
            currentUser = data.user;
        } catch (error) {
            console.error('Error al cargar usuario:', error);
        }
    }

    // Cargar reservas del usuario
    async function loadBookings() {
        try {
            const response = await fetch('/api/bookings');
            const allBookings = await response.json();
            
            // Filtrar solo las reservas del usuario actual
            if (currentUser) {
                bookingsData = allBookings.filter(booking => 
                    booking.user_name === currentUser.username || 
                    booking.user_email === currentUser.email
                );
            }
            
            updateBookingsList();
        } catch (error) {
            console.error('Error al cargar reservas:', error);
        }
    }

    // Cargar canchas recomendadas
    async function loadRecommendedCourts() {
        try {
            const response = await fetch('/api/courts');
            courtsData = await response.json();
            
            // Mostrar primeras 4 canchas como recomendadas
            const recommendedCourts = courtsData.slice(0, 4);
            updateRecommendedCourts(recommendedCourts);
        } catch (error) {
            console.error('Error al cargar canchas recomendadas:', error);
        }
    }

    // Actualizar lista de reservas
    function updateBookingsList() {
        const bookingsList = document.getElementById('bookings-list');
        if (!bookingsList) return;
        
        if (bookingsData.length === 0) {
            bookingsList.innerHTML = '<p>No tienes reservas aún. <a href="#" onclick="showBookingModal()">Haz tu primera reserva</a></p>';
            return;
        }
        
        bookingsList.innerHTML = bookingsData.map(booking => `
            <div class="booking-card">
                <div class="booking-info">
                    <h4>${booking.court_name}</h4>
                    <p><i class="fas fa-calendar"></i> ${booking.date}</p>
                    <p><i class="fas fa-clock"></i> ${booking.start_time} - ${booking.end_time}</p>
                    <p><i class="fas fa-map-marker-alt"></i> Ubicación: ${booking.court_name}</p>
                </div>
                <div>
                    <span class="booking-status status-${booking.status}">${getStatusText(booking.status)}</span>
                    ${booking.status === 'pending' ? `
                        <button class="btn-action btn-cancel" onclick="cancelBooking(${booking.id})" style="margin-left: 10px;">
                            <i class="fas fa-times"></i> Cancelar
                        </button>
                    ` : ''}
                </div>
            </div>
        `).join('');
    }

    // Actualizar canchas recomendadas
    function updateRecommendedCourts(courts) {
        const courtsGrid = document.getElementById('recommended-courts');
        if (!courtsGrid) return;
        
        courtsGrid.innerHTML = courts.map(court => `
            <div class="court-card">
                <div class="court-image" style="background-image: url('${court.image}')"></div>
                <div class="court-info">
                    <h4>${court.name}</h4>
                    <p><i class="fas fa-map-marker-alt"></i> ${court.location}</p>
                    <p><i class="fas fa-tag"></i> ${court.type}</p>
                    <p><i class="fas fa-dollar-sign"></i> ${court.price}/hora</p>
                    <p><i class="fas fa-star"></i> ${court.rating}</p>
                    <div style="margin-top: 15px;">
                        <button class="btn btn-primary btn-sm" onclick="bookCourt(${court.id}, '${court.name}')">
                            <i class="fas fa-calendar-plus"></i> Reservar
                        </button>
                    </div>
                </div>
            </div>
        `).join('');
    }

    // Obtener texto del estado
    function getStatusText(status) {
        const statusMap = {
            'pending': 'Pendiente',
            'confirmed': 'Confirmada',
            'cancelled': 'Cancelada'
        };
        return statusMap[status] || status;
    }

    // Mostrar modal de reserva
    function showBookingModal() {
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
                <h2>Nueva Reserva</h2>
                <form id="new-booking-form">
                    <div class="form-group">
                        <label>Cancha</label>
                        <select name="court_id" required>
                            <option value="">Selecciona una cancha</option>
                            ${courtsData.map(court => `
                                <option value="${court.id}">${court.name} - ${court.location}</option>
                            `).join('')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Fecha</label>
                        <input type="date" name="date" required>
                    </div>
                    <div class="form-group">
                        <label>Hora inicio</label>
                        <input type="time" name="start_time" required>
                    </div>
                    <div class="form-group">
                        <label>Hora fin</label>
                        <input type="time" name="end_time" required>
                    </div>
                    <div style="display: flex; gap: 10px; margin-top: 20px;">
                        <button type="submit" class="btn btn-primary">Reservar</button>
                        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancelar</button>
                    </div>
                </form>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Manejar envío del formulario
        document.getElementById('new-booking-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            await submitNewBooking(new FormData(e.target));
        });
    }

    // Enviar nueva reserva
    async function submitNewBooking(formData) {
        const bookingData = {
            court_id: parseInt(formData.get('court_id')),
            date: formData.get('date'),
            start_time: formData.get('start_time'),
            end_time: formData.get('end_time')
        };
        
        try {
            const response = await fetch('/book', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(bookingData)
            });
            
            const result = await response.json();
            
            if (result.success) {
                showNotification('Reserva realizada con éxito', 'success');
                closeModal();
                loadBookings();
            } else {
                showNotification(result.message, 'error');
            }
        } catch (error) {
            console.error('Error al realizar reserva:', error);
            showNotification('Error al realizar la reserva', 'error');
        }
    }

    // Reservar cancha específica
    function bookCourt(courtId, courtName) {
        showBookingModal();
        // Pre-seleccionar la cancha
        setTimeout(() => {
            const courtSelect = document.querySelector('select[name="court_id"]');
            if (courtSelect) {
                courtSelect.value = courtId;
            }
        }, 100);
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
                    loadBookings();
                } else {
                    showNotification('Error al cancelar reserva', 'error');
                }
            } catch (error) {
                console.error('Error al cancelar reserva:', error);
                showNotification('Error al cancelar reserva', 'error');
            }
        }
    }

    // Cerrar modal
    function closeModal() {
        const modal = document.querySelector('.modal');
        if (modal) modal.remove();
    }

    // Inicializar al cargar la página
    document.addEventListener('DOMContentLoaded', () => {
        loadUserData();
        
        // Agregar animaciones CSS
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideOut {
                to {
                    transform: translateX(100%);
                    opacity: 0;
                }
            }
            
            .modal {
                animation: fadeIn 0.3s ease-out;
            }
            
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            
            .form-group {
                margin-bottom: 15px;
            }
            
            .form-group label {
                display: block;
                margin-bottom: 5px;
                font-weight: 500;
            }
            
            .form-group input, .form-group select {
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 5px;
                font-size: 1rem;
            }
            
            .btn-sm {
                padding: 5px 10px;
                font-size: 0.8rem;
            }
        `;
        document.head.appendChild(style);
    });
    
} // Fin del condicional - solo ejecutar en páginas de usuario

// Funciones globales para que estén disponibles siempre
function showBookingModal() {
    console.log('showBookingModal llamado');
    // Si estamos en el dashboard de usuario
    if (document.getElementById('user-dashboard')) {
        // Cargar datos de canchas si no están cargados
        if (typeof courtsData === 'undefined' || courtsData.length === 0) {
            loadCourtsForModal();
        } else {
            createBookingModal();
        }
    } else {
        alert('Función de reserva (funcionalidad próximamente)');
    }
}

// Función para cargar canchas y mostrar modal
async function loadCourtsForModal() {
    try {
        const response = await fetch('/api/courts');
        const courts = await response.json();
        window.courtsData = courts; // Hacer disponible globalmente
        createBookingModal();
    } catch (error) {
        console.error('Error al cargar canchas:', error);
        alert('Error al cargar canchas');
    }
}

// Función para crear el modal
function createBookingModal() {
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
            <h2>Nueva Reserva de Fútbol</h2>
            <form id="new-booking-form">
                <div class="form-group">
                    <label>Tipo de Cancha</label>
                    <select name="court_id" required>
                        <option value="">Selecciona tipo de cancha</option>
                        <option value="futbol-5">Fútbol 5</option>
                        <option value="futbol-7">Fútbol 7</option>
                        <option value="futbol-11">Fútbol 11</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Fecha</label>
                    <input type="date" name="date" required>
                </div>
                <div class="form-group">
                    <label>Hora inicio</label>
                    <input type="time" name="start_time" required>
                </div>
                <div class="form-group">
                    <label>Hora fin</label>
                    <input type="time" name="end_time" required>
                </div>
                <div style="display: flex; gap: 10px; margin-top: 20px;">
                    <button type="submit" class="btn btn-primary">Reservar</button>
                    <button type="button" class="btn btn-outline" onclick="closeModal()">Cancelar</button>
                </div>
            </form>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Manejar envío del formulario
    document.getElementById('new-booking-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const bookingData = {
            court_id: parseInt(formData.get('court_id')),
            date: formData.get('date'),
            start_time: formData.get('start_time'),
            end_time: formData.get('end_time')
        };
        
        try {
            const response = await fetch('/book', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(bookingData)
            });
            
            const result = await response.json();
            
            if (result.success) {
                alert('Reserva realizada con éxito');
                closeModal();
                // Recargar la página para mostrar la nueva reserva
                window.location.reload();
            } else {
                alert(result.message);
            }
        } catch (error) {
            console.error('Error al realizar reserva:', error);
            alert('Error al realizar la reserva');
        }
    });
}

function browseCourts() {
    console.log('browseCourts llamado');
    window.location.href = '/#canchas';
}

function editProfile() {
    console.log('editProfile llamado');
    // Mostrar modal para editar perfil
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
            <h2>Editar Perfil</h2>
            <form id="edit-profile-form">
                <div class="form-group">
                    <label>Nombre de usuario</label>
                    <input type="text" name="username" value="{{ user.username }}" readonly>
                    <small>El nombre de usuario no se puede cambiar</small>
                </div>
                <div class="form-group">
                    <label>Email</label>
                    <input type="email" name="email" value="{{ user.email }}" readonly>
                    <small>El email no se puede cambiar</small>
                </div>
                <div class="form-group">
                    <label>Nueva contraseña (opcional)</label>
                    <input type="password" name="password" placeholder="Dejar en blanco para no cambiar">
                </div>
                <div class="form-group">
                    <label>Confirmar contraseña</label>
                    <input type="password" name="confirm_password" placeholder="Confirmar nueva contraseña">
                </div>
                <div style="display: flex; gap: 10px; margin-top: 20px;">
                    <button type="submit" class="btn btn-primary">Guardar cambios</button>
                    <button type="button" class="btn btn-outline" onclick="closeModal()">Cancelar</button>
                </div>
            </form>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Manejar envío del formulario
    document.getElementById('edit-profile-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const password = formData.get('password');
        const confirmPassword = formData.get('confirm_password');
        
        if (password && password !== confirmPassword) {
            alert('Las contraseñas no coinciden');
            return;
        }
        
        if (!password) {
            alert('No se realizaron cambios');
            closeModal();
            return;
        }
        
        try {
            const response = await fetch('/api/update-password', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ password: password })
            });
            
            const result = await response.json();
            
            if (result.success) {
                alert('Contraseña actualizada correctamente');
                closeModal();
            } else {
                alert(result.message || 'Error al actualizar contraseña');
            }
        } catch (error) {
            console.error('Error al actualizar perfil:', error);
            alert('Error al actualizar perfil');
        }
    });
}

function showHistory() {
    console.log('showHistory llamado');
    // Mostrar modal con historial completo
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
            max-width: 800px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
        ">
            <h2>Historial Completo de Reservas</h2>
            <div id="history-content">
                <p>Cargando historial...</p>
            </div>
            <div style="margin-top: 20px;">
                <button type="button" class="btn btn-outline" onclick="closeModal()">Cerrar</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Cargar historial de reservas
    loadHistoryData();
}

async function loadHistoryData() {
    try {
        const response = await fetch('/api/bookings');
        const allBookings = await response.json();
        
        // Obtener información del usuario actual
        const userResponse = await fetch('/api/current-user');
        const userData = await userResponse.json();
        const currentUser = userData.user;
        
        // Filtrar reservas del usuario
        const userBookings = allBookings.filter(booking => 
            booking.user_name === currentUser.username || 
            booking.user_email === currentUser.email
        );
        
        const historyContent = document.getElementById('history-content');
        
        if (userBookings.length === 0) {
            historyContent.innerHTML = '<p>No tienes reservas en tu historial.</p>';
            return;
        }
        
        // Ordenar por fecha (más reciente primero)
        userBookings.sort((a, b) => new Date(b.date) - new Date(a.date));
        
        historyContent.innerHTML = `
            <div class="history-list">
                ${userBookings.map(booking => `
                    <div class="history-item" style="
                        border: 1px solid #ddd;
                        padding: 15px;
                        margin-bottom: 10px;
                        border-radius: 5px;
                        background: #f9f9f9;
                    ">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <h4>${booking.court_name}</h4>
                                <p><i class="fas fa-calendar"></i> ${booking.date}</p>
                                <p><i class="fas fa-clock"></i> ${booking.start_time} - ${booking.end_time}</p>
                                <p><i class="fas fa-map-marker-alt"></i> ${booking.court_name}</p>
                            </div>
                            <div>
                                <span class="booking-status status-${booking.status}" style="
                                    padding: 5px 10px;
                                    border-radius: 3px;
                                    font-size: 0.8rem;
                                    font-weight: bold;
                                    ${getStatusStyle(booking.status)}
                                ">
                                    ${getStatusText(booking.status)}
                                </span>
                            </div>
                        </div>
                        <div style="margin-top: 10px; font-size: 0.9rem; color: #666;">
                            Creada: ${new Date(booking.created_at).toLocaleString()}
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    } catch (error) {
        console.error('Error al cargar historial:', error);
        document.getElementById('history-content').innerHTML = '<p>Error al cargar el historial.</p>';
    }
}

function getStatusStyle(status) {
    const styles = {
        'pending': 'background: #fff3cd; color: #856404;',
        'confirmed': 'background: #d4edda; color: #155724;',
        'cancelled': 'background: #f8d7da; color: #721c24;'
    };
    return styles[status] || 'background: #e2e3e5; color: #383d41;';
}

// Función global para obtener texto del estado
function getStatusText(status) {
    const statusMap = {
        'pending': 'Pendiente',
        'confirmed': 'Confirmada',
        'cancelled': 'Cancelada'
    };
    return statusMap[status] || status;
}

function closeModal() {
    const modal = document.querySelector('.modal');
    if (modal) modal.remove();
}
