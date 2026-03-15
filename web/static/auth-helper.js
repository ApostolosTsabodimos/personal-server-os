// auth-helper.js
// Add this to your dashboard's app.js

// Auth helper functions
const Auth = {
    getToken() {
        return localStorage.getItem('pso_token');
    },

    getUser() {
        const userStr = localStorage.getItem('pso_user');
        return userStr ? JSON.parse(userStr) : null;
    },

    isLoggedIn() {
        return !!this.getToken();
    },

    logout() {
        // Call logout API
        fetch('/api/auth/logout', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.getToken()}`
            }
        }).finally(() => {
            localStorage.removeItem('pso_token');
            localStorage.removeItem('pso_user');
            window.location.href = '/login';
        });
    },

    // Add token to fetch requests
    fetch(url, options = {}) {
        const token = this.getToken();
        
        if (!token) {
            window.location.href = '/login';
            return Promise.reject('Not authenticated');
        }

        // Add Authorization header
        options.headers = {
            ...options.headers,
            'Authorization': `Bearer ${token}`
        };

        return fetch(url, options).then(response => {
            // If unauthorized, redirect to login
            if (response.status === 401) {
                localStorage.removeItem('pso_token');
                localStorage.removeItem('pso_user');
                window.location.href = '/login';
                throw new Error('Session expired');
            }
            return response;
        });
    }
};

// Check authentication on page load
window.addEventListener('load', async () => {
    if (!Auth.isLoggedIn()) {
        window.location.href = '/login';
        return;
    }

    // Validate token
    try {
        const response = await Auth.fetch('/api/auth/validate');
        if (!response.ok) {
            window.location.href = '/login';
        }
    } catch (error) {
        window.location.href = '/login';
    }
});

// Example: Replace all fetch calls in your dashboard
// Old: fetch('/api/services')
// New: Auth.fetch('/api/services')

/*
USAGE IN YOUR DASHBOARD (app.js):

// Get services with auth
async function loadServices() {
    try {
        const response = await Auth.fetch('/api/services');
        const data = await response.json();
        // ... render services
    } catch (error) {
        console.error('Failed to load services:', error);
    }
}

// Start a service with auth
async function startService(serviceId) {
    try {
        const response = await Auth.fetch(`/api/services/${serviceId}/start`, {
            method: 'POST'
        });
        const data = await response.json();
        // ... handle response
    } catch (error) {
        console.error('Failed to start service:', error);
    }
}

// Add logout button to your dashboard
<button onclick="Auth.logout()">Logout</button>
*/