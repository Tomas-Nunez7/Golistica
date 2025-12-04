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
    
    // Eventos de pagos
    socket.on('payment_successful', (data) => {
        showNotification(`¡Seña procesada correctamente! ID: ${data.transaction_id}`, 'success');
        loadBookings();
        loadUserPayments();
    });
    
    socket.on('payment_failed', (data) => {
        showNotification(`Pago rechazado: ${data.error}`, 'error');
        loadBookings();
    });
    
    socket.on('payment_error', (data) => {
        showNotification(`Error en pago: ${data.error}`, 'error');
        loadBookings();
    });
    
    // Unirse a sala de usuario para notificaciones personalizadas
    socket.on('connect', () => {
        socket.emit('join_user_room', {user_id: currentUser?.id});
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
            loadRecommendedCourts(),
            loadUserPayments()
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
        
        console.log('DEBUG - bookingsData:', bookingsData);
        
        if (bookingsData.length === 0) {
            bookingsList.innerHTML = '<p>No tienes reservas aún. <a href="#" onclick="showBookingModal()">Haz tu primera reserva</a></p>';
            return;
        }
        
        bookingsList.innerHTML = bookingsData.map(booking => {
            console.log('DEBUG - booking individual:', booking);
            const showPayButton = (!booking.payment_status || booking.payment_status === 'pending');
            console.log('DEBUG - showPayButton:', showPayButton, 'status:', booking.status, 'payment_status:', booking.payment_status);
            
            return `
            <div class="booking-card">
                <div class="booking-info">
                    <h4>${booking.court_name}</h4>
                    <p><i class="fas fa-calendar"></i> ${booking.date}</p>
                    <p><i class="fas fa-clock"></i> ${booking.start_time} - ${booking.end_time}</p>
                    <p><i class="fas fa-map-marker-alt"></i> Ubicación: ${booking.court_name}</p>
                    <p><i class="fas fa-dollar-sign"></i> Total: $${booking.total_amount || 'N/A'}</p>
                    <p><i class="fas fa-credit-card"></i> Seña: $${booking.deposit_amount || 'N/A'}</p>
                    <p><i class="fas fa-info-circle"></i> Pago: ${getPaymentStatusText(booking.payment_status)}</p>
                </div>
                <div>
                    <span class="booking-status status-${booking.status}">${getStatusText(booking.status)}</span>
                    ${showPayButton ? `
                        <button class="btn-action btn-pay" onclick="payDeposit(${booking.id})" style="margin-left: 10px; background: #28a745;">
                            <i class="fas fa-credit-card"></i> Pagar Seña
                        </button>
                    ` : ''}
                    ${booking.status === 'pending' && !showPayButton ? `
                        <button class="btn-action btn-cancel" onclick="cancelBooking(${booking.id})" style="margin-left: 10px;">
                            <i class="fas fa-times"></i> Cancelar
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
        }).join('');
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
    
    // Obtener texto del estado de pago
    function getPaymentStatusText(payment_status) {
        const statusMap = {
            'pending': 'Pendiente de pago',
            'paid': 'Pagado',
            'refunded': 'Reembolsado'
        };
        return statusMap[payment_status] || payment_status;
    }
    
    // Cargar pagos del usuario
    async function loadUserPayments() {
        try {
            const response = await fetch('/api/payments/user');
            const data = await response.json();
            
            if (data.success) {
                window.userPayments = data.payments;
                console.log('Pagos cargados:', data.payments);
            }
        } catch (error) {
            console.error('Error al cargar pagos:', error);
        }
    }
    
    // Pagar seña de reserva
    async function payDeposit(bookingId) {
        // Mostrar modal de pago
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
        
        // Obtener información de la reserva
        const booking = bookingsData.find(b => b.id === bookingId);
        const depositAmount = booking?.deposit_amount || 0;
        
        modal.innerHTML = `
            <div class="modal-content" style="
                background: white;
                padding: 30px;
                border-radius: 10px;
                max-width: 500px;
                width: 90%;
            ">
                <h2>Pagar Seña de Reserva</h2>
                <div style="margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 5px;">
                    <p><strong>Reserva:</strong> ${booking?.court_name || 'N/A'}</p>
                    <p><strong>Fecha:</strong> ${booking?.date || 'N/A'}</p>
                    <p><strong>Horario:</strong> ${booking?.start_time || 'N/A'} - ${booking?.end_time || 'N/A'}</p>
                    <p><strong>Total:</strong> $${booking?.total_amount || 'N/A'}</p>
                    <p><strong><i class="fas fa-credit-card"></i> Seña a pagar (50%):</strong> <span style="color: #28a745; font-size: 1.2rem; font-weight: bold;">$${depositAmount}</span></p>
                </div>
                <form id="payment-form">
                    <div class="form-group">
                        <label>Método de pago</label>
                        <select name="payment_method" required>
                            <option value="credit_card">Tarjeta de crédito</option>
                            <option value="debit_card">Tarjeta de débito</option>
                            <option value="transfer">Transferencia bancaria</option>
                        </select>
                    </div>
                    <div style="margin: 20px 0; padding: 15px; background: #fff3cd; border-radius: 5px;">
                        <p><i class="fas fa-info-circle"></i> <strong>Información importante:</strong></p>
                        <ul style="margin: 10px 0; padding-left: 20px;">
                            <li>El procesamiento tomará 3-5 segundos</li>
                            <li>Recibirás una notificación cuando se complete</li>
                            <li>La reserva se confirmará automáticamente si el pago es aprobado</li>
                            <li>Si el pago es rechazado, la reserva será cancelada</li>
                        </ul>
                    </div>
                    <div style="display: flex; gap: 10px; margin-top: 20px;">
                        <button type="submit" class="btn btn-primary" style="background: #28a745;">
                            <i class="fas fa-credit-card"></i> Pagar Seña
                        </button>
                        <button type="button" class="btn btn-outline" onclick="closeModal()">Cancelar</button>
                    </div>
                </form>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Manejar envío del formulario
        document.getElementById('payment-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const paymentMethod = formData.get('payment_method');
            
            await submitDepositPayment(bookingId, paymentMethod);
        });
    }
    
    // Enviar pago de seña
    async function submitDepositPayment(bookingId, paymentMethod) {
        try {
            const response = await fetch('/api/payments/deposit', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    booking_id: bookingId,
                    payment_method: paymentMethod
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                showNotification('Procesando pago de seña...', 'info');
                closeModal();
                
                // Mostrar indicador de progreso
                showPaymentProgress(result.payment_id, result.amount);
                
                // Verificar estado del pago periódicamente
                checkPaymentStatus(result.payment_id);
            } else {
                showNotification(result.message, 'error');
            }
        } catch (error) {
            console.error('Error al procesar pago:', error);
            showNotification('Error al procesar el pago', 'error');
        }
    }
    
    // Mostrar progreso de pago
    function showPaymentProgress(paymentId, amount) {
        const progressDiv = document.createElement('div');
        progressDiv.id = `payment-progress-${paymentId}`;
        progressDiv.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            z-index: 1001;
            max-width: 300px;
        `;
        progressDiv.innerHTML = `
            <h4><i class="fas fa-credit-card"></i> Procesando Pago</h4>
            <p>Seña: $${amount}</p>
            <p>ID: ${paymentId}</p>
            <div style="margin: 10px 0;">
                <div style="background: #e9ecef; border-radius: 5px; height: 8px; overflow: hidden;">
                    <div style="background: #28a745; height: 100%; width: 0%; transition: width 0.3s; animation: pulse 1.5s infinite;"></div>
                </div>
            </div>
            <p style="font-size: 0.9rem; color: #666;">Procesando... (3-5 segundos)</p>
        `;
        
        document.body.appendChild(progressDiv);
    }
    
    // Verificar estado del pago
    async function checkPaymentStatus(paymentId) {
        const maxAttempts = 10;
        let attempts = 0;
        
        const checkStatus = async () => {
            try {
                const response = await fetch(`/api/payments/${paymentId}/status`);
                const data = await response.json();
                
                if (data.success) {
                    const payment = data.payment;
                    
                    if (payment.status === 'completed') {
                        // Éxito
                        const progressDiv = document.getElementById(`payment-progress-${paymentId}`);
                        if (progressDiv) {
                            progressDiv.innerHTML = `
                                <h4><i class="fas fa-check-circle" style="color: #28a745;"></i> Pago Exitoso</h4>
                                <p>Seña: $${payment.amount}</p>
                                <p>Transacción: ${payment.transaction_id}</p>
                                <p style="color: #28a745; font-weight: bold;">¡Reserva confirmada!</p>
                            `;
                            setTimeout(() => progressDiv.remove(), 5000);
                        }
                        
                        showNotification('Pago creado con éxito. Tu reserva está confirmada.', 'success');
                        loadBookings();
                        return;
                    } else if (payment.status === 'failed') {
                        // Fracaso
                        const progressDiv = document.getElementById(`payment-progress-${paymentId}`);
                        if (progressDiv) {
                            progressDiv.innerHTML = `
                                <h4><i class="fas fa-times-circle" style="color: #dc3545;"></i> Pago Rechazado</h4>
                                <p>Seña: $${payment.amount}</p>
                                <p style="color: #dc3545;">${payment.error_message}</p>
                                <p style="color: #dc3545; font-weight: bold;">Reserva cancelada</p>
                            `;
                            setTimeout(() => progressDiv.remove(), 5000);
                        }
                        
                        showNotification('Pago rechazado. Tu reserva ha sido cancelada.', 'error');
                        loadBookings();
                        return;
                    }
                }
                
                // Si sigue pendiente, continuar verificando
                attempts++;
                if (attempts < maxAttempts) {
                    setTimeout(checkStatus, 1000); // Verificar cada segundo
                } else {
                    // Timeout
                    const progressDiv = document.getElementById(`payment-progress-${paymentId}`);
                    if (progressDiv) {
                        progressDiv.innerHTML = `
                            <h4><i class="fas fa-exclamation-triangle" style="color: #ffc107;"></i> Tiempo de espera</h4>
                            <p>El pago está tardando más de lo esperado</p>
                            <p>Por favor, verifica el estado más tarde</p>
                        `;
                        setTimeout(() => progressDiv.remove(), 3000);
                    }
                }
                
            } catch (error) {
                console.error('Error verificando estado del pago:', error);
                attempts++;
                if (attempts < maxAttempts) {
                    setTimeout(checkStatus, 1000);
                }
            }
        };
        
        // Iniciar verificación después de un breve retraso
        setTimeout(checkStatus, 1000);
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
                console.log('DEBUG - Mostrando notificación de reserva exitosa');
                // Usar la función global showNotification
                window.showNotification('Reserva creada con éxito', 'success');
                closeModal();
                loadBookings();
            } else {
                window.showNotification(result.message, 'error');
            }
        } catch (error) {
            console.error('Error al realizar reserva:', error);
            window.showNotification('Error al realizar la reserva', 'error');
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
function showNotification(message, type = 'info') {
    const notificationArea = document.getElementById('notification-area');
    if (!notificationArea) {
        // Crear área de notificaciones si no existe
        const div = document.createElement('div');
        div.id = 'notification-area';
        div.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
        `;
        document.body.appendChild(div);
    }
    
    // Agregar CSS para animaciones si no existe
    if (!document.getElementById('notification-styles')) {
        const style = document.createElement('style');
        style.id = 'notification-styles';
        style.textContent = `
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOut {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(100%); opacity: 0; }
            }
        `;
        document.head.appendChild(style);
    }
    
    const notification = document.createElement('div');
    notification.className = 'notification';
    notification.style.cssText = `
        background: ${type === 'success' ? '#28a745' : type === 'error' ? '#dc3545' : type === 'warning' ? '#ffc107' : '#17a2b8'};
        color: white;
        padding: 15px 20px;
        margin-bottom: 10px;
        border-radius: 5px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        animation: slideIn 0.3s ease-out;
    `;
    notification.innerHTML = `
        <strong>${type.charAt(0).toUpperCase() + type.slice(1)}</strong>
        <p style="margin: 5px 0 0 0;">${message}</p>
    `;
    
    const area = document.getElementById('notification-area');
    area.appendChild(notification);
    
    // Auto-eliminar después de 5 segundos
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}

function closeModal() {
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => modal.remove());
}

function payDeposit(bookingId) {
    // Verificar si estamos en la página de usuario
    if (!document.getElementById('user-dashboard')) {
        alert('Debes estar en tu perfil para procesar pagos');
        return;
    }
    
    // Obtener datos de reservas si no están cargados
    if (typeof bookingsData === 'undefined' || bookingsData.length === 0) {
        // Cargar datos directamente
        fetch('/api/bookings')
            .then(response => response.json())
            .then(allBookings => {
                // Obtener usuario actual
                return fetch('/api/current-user')
                    .then(response => response.json())
                    .then(userData => {
                        // Filtrar reservas del usuario
                        const userBookings = allBookings.filter(booking => 
                            booking.user_name === userData.user.username || 
                            booking.user_email === userData.user.email
                        );
                        window.bookingsData = userBookings;
                        payDeposit(bookingId);
                    });
            })
            .catch(error => {
                console.error('Error cargando datos:', error);
                alert('Error cargando datos de reservas');
            });
        return;
    }
    
    // Mostrar modal de pago
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
    
    // Obtener información de la reserva
    const booking = bookingsData.find(b => b.id === bookingId);
    const depositAmount = booking?.deposit_amount || 0;
    
    modal.innerHTML = `
        <div class="modal-content" style="
            background: white;
            padding: 30px;
            border-radius: 10px;
            max-width: 500px;
            width: 90%;
        ">
            <h2>Pagar Seña de Reserva</h2>
            <div style="margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 5px;">
                <p><strong>Reserva:</strong> ${booking?.court_name || 'N/A'}</p>
                <p><strong>Fecha:</strong> ${booking?.date || 'N/A'}</p>
                <p><strong>Horario:</strong> ${booking?.start_time || 'N/A'} - ${booking?.end_time || 'N/A'}</p>
                <p><strong>Total:</strong> $${booking?.total_amount || 'N/A'}</p>
                <p><strong><i class="fas fa-credit-card"></i> Seña a pagar (50%):</strong> <span style="color: #28a745; font-size: 1.2rem; font-weight: bold;">$${depositAmount}</span></p>
            </div>
            <form id="payment-form">
                <div class="form-group">
                    <label>Método de pago</label>
                    <select name="payment_method" required>
                        <option value="credit_card">Tarjeta de crédito</option>
                        <option value="debit_card">Tarjeta de débito</option>
                        <option value="transfer">Transferencia bancaria</option>
                    </select>
                </div>
                <div style="margin: 20px 0; padding: 15px; background: #fff3cd; border-radius: 5px;">
                    <p><i class="fas fa-info-circle"></i> <strong>Información importante:</strong></p>
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        <li>El procesamiento tomará 3-5 segundos</li>
                        <li>Recibirás una notificación cuando se complete</li>
                        <li>La reserva se confirmará automáticamente si el pago es aprobado</li>
                        <li>Si el pago es rechazado, la reserva será cancelada</li>
                    </ul>
                </div>
                <div style="display: flex; gap: 10px; margin-top: 20px;">
                    <button type="submit" class="btn btn-primary" style="background: #28a745;">
                        <i class="fas fa-credit-card"></i> Pagar Seña
                    </button>
                    <button type="button" class="btn btn-outline" onclick="closeModal()">Cancelar</button>
                </div>
            </form>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Manejar envío del formulario
    document.getElementById('payment-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const paymentMethod = formData.get('payment_method');
        
        await submitDepositPayment(bookingId, paymentMethod);
    });
}

async function submitDepositPayment(bookingId, paymentMethod) {
    try {
        const payload = {
            booking_id: bookingId,
            payment_method: paymentMethod
        };
        
        console.log('DEBUG - Enviando pago:', payload);
        
        const response = await fetch('/api/payments/deposit', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload)
        });
        
        console.log('DEBUG - Response status:', response.status);
        const result = await response.json();
        console.log('DEBUG - Response data:', result);
        
        if (result.success) {
            closeModal();
            
            // Verificar si el pago fue aprobado o rechazado
            if (result.payment_status === 'completed') {
                console.log('DEBUG - Mostrando notificación de éxito');
                showNotification('Pago creado con éxito. Tu reserva está confirmada.', 'success');
                if (typeof loadBookings === 'function') loadBookings();
            } else if (result.payment_status === 'failed') {
                console.log('DEBUG - Mostrando notificación de error');
                showNotification('Pago rechazado. Tu reserva ha sido cancelada.', 'error');
                if (typeof loadBookings === 'function') loadBookings();
            } else {
                console.log('DEBUG - Estado desconocido:', result.payment_status);
                showNotification('Estado de pago desconocido', 'warning');
            }
        } else {
            showNotification(result.message, 'error');
        }
    } catch (error) {
        console.error('Error al procesar pago:', error);
        showNotification('Error al procesar el pago', 'error');
    }
}

function showPaymentProgress(paymentId, amount) {
    const progressDiv = document.createElement('div');
    progressDiv.id = `payment-progress-${paymentId}`;
    progressDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        z-index: 1001;
        max-width: 300px;
    `;
    progressDiv.innerHTML = `
        <h4><i class="fas fa-credit-card"></i> Procesando Pago</h4>
        <p>Seña: $${amount}</p>
        <p>ID: ${paymentId}</p>
        <div style="margin: 10px 0;">
            <div style="background: #e9ecef; border-radius: 5px; height: 8px; overflow: hidden;">
                <div style="background: #28a745; height: 100%; width: 0%; transition: width 0.3s; animation: pulse 1.5s infinite;"></div>
            </div>
        </div>
        <p style="font-size: 0.9rem; color: #666;">Procesando... (3-5 segundos)</p>
    `;
    
    document.body.appendChild(progressDiv);
}

async function checkPaymentStatus(paymentId) {
    const maxAttempts = 20; // Aumentar a 20 segundos
    let attempts = 0;
    
    const checkStatus = async () => {
        try {
            const response = await fetch(`/api/payments/${paymentId}/status`);
            const data = await response.json();
            
            if (data.success) {
                const payment = data.payment;
                
                if (payment.status === 'completed') {
                    // Éxito
                    const progressDiv = document.getElementById(`payment-progress-${paymentId}`);
                    if (progressDiv) {
                        progressDiv.innerHTML = `
                            <h4><i class="fas fa-check-circle" style="color: #28a745;"></i> Pago Exitoso</h4>
                            <p>Seña: $${payment.amount}</p>
                            <p>Transacción: ${payment.transaction_id}</p>
                            <p style="color: #28a745; font-weight: bold;">¡Reserva confirmada!</p>
                        `;
                        setTimeout(() => progressDiv.remove(), 5000);
                    }
                    
                    showNotification('Pago creado con éxito. Tu reserva está confirmada.', 'success');
                    if (typeof loadBookings === 'function') loadBookings();
                    return;
                } else if (payment.status === 'failed') {
                    // Fracaso
                    const progressDiv = document.getElementById(`payment-progress-${paymentId}`);
                    if (progressDiv) {
                        progressDiv.innerHTML = `
                            <h4><i class="fas fa-times-circle" style="color: #dc3545;"></i> Pago Rechazado</h4>
                            <p>Seña: $${payment.amount}</p>
                            <p style="color: #dc3545;">${payment.error_message}</p>
                            <p style="color: #dc3545; font-weight: bold;">Reserva cancelada</p>
                        `;
                        setTimeout(() => progressDiv.remove(), 5000);
                    }
                    
                    showNotification('Pago rechazado. Tu reserva ha sido cancelada.', 'error');
                    if (typeof loadBookings === 'function') loadBookings();
                    return;
                }
            }
            
            // Si sigue pendiente, continuar verificando
            attempts++;
            if (attempts < maxAttempts) {
                setTimeout(checkStatus, 1000); // Verificar cada segundo
            } else {
                // Timeout
                const progressDiv = document.getElementById(`payment-progress-${paymentId}`);
                if (progressDiv) {
                    progressDiv.innerHTML = `
                        <h4><i class="fas fa-exclamation-triangle" style="color: #ffc107;"></i> Tiempo de espera</h4>
                        <p>El pago está tardando más de lo esperado</p>
                        <p>Por favor, verifica el estado más tarde</p>
                    `;
                    setTimeout(() => progressDiv.remove(), 3000);
                }
            }
            
        } catch (error) {
            console.error('Error verificando estado del pago:', error);
            attempts++;
            if (attempts < maxAttempts) {
                setTimeout(checkStatus, 1000);
            }
        }
    };
    
    // Iniciar verificación después de un breve retraso
    setTimeout(checkStatus, 1000);
}

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
                window.showNotification('Reserva creada con éxito', 'success');
                closeModal();
                // Recargar la página para mostrar la nueva reserva
                window.location.reload();
            } else {
                window.showNotification(result.message, 'error');
            }
        } catch (error) {
            console.error('Error al realizar reserva:', error);
            window.showNotification('Error al realizar la reserva', 'error');
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
