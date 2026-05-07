// Shared JavaScript for all pages
const API_BASE_URL = 'http://127.0.0.1:5000';

// Check if user is logged in
function checkAuth() {
    const token = localStorage.getItem('adminToken');
    const currentPage = window.location.pathname.split('/').pop();
    
    // Redirect to login if not authenticated and not on login page
    if (!token && currentPage !== 'login.html' && currentPage !== 'index.html') {
        window.location.href = 'login.html';
        return false;
    }
    return true;
}

// Show loading spinner
function showLoading(containerId) {
    const container = document.getElementById(containerId);
    if (container) {
        container.innerHTML = '<div class="spinner"></div>';
    }
}

// Show alert message
function showAlert(message, type = 'info', containerId = 'alert-container') {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type}`;
    alertDiv.innerHTML = `
        <i class="fas ${getAlertIcon(type)}"></i>
        <span>${message}</span>
        <button class="close-btn" onclick="this.parentElement.remove()">&times;</button>
    `;
    
    container.innerHTML = '';
    container.appendChild(alertDiv);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        if (alertDiv.parentElement) {
            alertDiv.remove();
        }
    }, 5000);
}

function getAlertIcon(type) {
    const icons = {
        success: 'fa-check-circle',
        danger: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };
    return icons[type] || icons.info;
}

// Format date
function formatDate(dateString) {
    const options = { year: 'numeric', month: 'short', day: 'numeric' };
    return new Date(dateString).toLocaleDateString(undefined, options);
}

// Format time
function formatTime(timeString) {
    return new Date(`2000-01-01T${timeString}`).toLocaleTimeString([], { 
        hour: '2-digit', 
        minute: '2-digit' 
    });
}

// Handle API errors
async function handleApiResponse(response) {
    if (!response.ok) {
        const error = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(error.error || `HTTP error! status: ${response.status}`);
    }
    return response.json();
}

// Webcam functions
async function startWebcam(videoElement) {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
            video: {
                width: 640,
                height: 480
            },
            audio: false 
        });
        videoElement.srcObject = stream;
        return stream;
    } catch (err) {
        throw new Error('Could not access webcam: ' + err.message);
    }
}

function stopWebcam(stream) {
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
    }
}

function captureImage(videoElement, canvasElement) {
    const context = canvasElement.getContext('2d');
    canvasElement.width = videoElement.videoWidth;
    canvasElement.height = videoElement.videoHeight;
    context.drawImage(videoElement, 0, 0, canvasElement.width, canvasElement.height);
    return canvasElement.toDataURL('image/jpeg');
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    
    // Add logout button functionality
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', (e) => {
            e.preventDefault();
            localStorage.removeItem('adminToken');
            window.location.href = 'login.html';
        });
    }
    
    // Add active class to current nav link
    const currentPage = window.location.pathname.split('/').pop();
    const navLinks = document.querySelectorAll('.navbar-menu a');
    navLinks.forEach(link => {
        if (link.getAttribute('href') === currentPage) {
            link.classList.add('active');
        }
    });
});

// Export functions for use in other files
window.showAlert = showAlert;
window.formatDate = formatDate;
window.formatTime = formatTime;
window.startWebcam = startWebcam;
window.stopWebcam = stopWebcam;
window.captureImage = captureImage;