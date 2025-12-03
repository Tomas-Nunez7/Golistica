// JavaScript específico para páginas de autenticación
// No inicializar Socket.IO en estas páginas

// Validación básica de formularios
document.addEventListener('DOMContentLoaded', function() {
    // Validar formulario de login
    const loginForm = document.querySelector('form[action="/login"]');
    if (loginForm) {
        loginForm.addEventListener('submit', function(e) {
            const username = document.getElementById('username').value.trim();
            const password = document.getElementById('password').value;
            
            if (!username || !password) {
                e.preventDefault();
                alert('Por favor completa todos los campos');
                return false;
            }
        });
    }
    
    // Validar formulario de registro
    const registerForm = document.querySelector('form[action="/register"]');
    if (registerForm) {
        registerForm.addEventListener('submit', function(e) {
            const username = document.getElementById('username').value.trim();
            const email = document.getElementById('email').value.trim();
            const password = document.getElementById('password').value;
            
            if (!username || !email || !password) {
                e.preventDefault();
                alert('Por favor completa todos los campos');
                return false;
            }
            
            if (password.length < 6) {
                e.preventDefault();
                alert('La contraseña debe tener al menos 6 caracteres');
                return false;
            }
        });
    }
});
