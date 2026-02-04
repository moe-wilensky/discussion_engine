/**
 * WebSocket client for real-time discussion updates.
 * Handles notifications, MRP timers, response alerts, and live updates.
 */

class DiscussionWebSocket {
    constructor(discussionId) {
        this.discussionId = discussionId;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 3000; // 3 seconds
        this.connect();
    }
    
    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        
        // Handle localhost development environment (web:8002, websocket:8003)
        let host = window.location.host;
        if (window.location.hostname === 'localhost' && window.location.port === '8002') {
            host = `${window.location.hostname}:8003`;
        }
        
        const wsUrl = `${protocol}//${host}/ws/discussions/${this.discussionId}/`;
        
        try {
            this.ws = new WebSocket(wsUrl);
            this.ws.onopen = () => this.onOpen();
            this.ws.onmessage = (e) => this.onMessage(e);
            this.ws.onerror = (e) => this.onError(e);
            this.ws.onclose = () => this.onClose();
        } catch (error) {
            console.error('WebSocket connection error:', error);
            this.scheduleReconnect();
        }
    }
    
    onOpen() {
        console.log(`WebSocket connected to discussion ${this.discussionId}`);
        this.reconnectAttempts = 0;
        
        // Show connection indicator
        const indicator = document.getElementById('ws-status');
        if (indicator) {
            indicator.className = 'ws-status connected';
            indicator.title = 'Connected - receiving real-time updates';
        }
    }
    
    onMessage(event) {
        try {
            const data = JSON.parse(event.data);
            console.log('WebSocket message:', data);
            
            switch(data.type) {
                case 'mrp_timer_update':
                    this.updateMRPTimer(data);
                    break;
                case 'new_response':
                    this.handleNewResponse(data);
                    break;
                case 'mrp_warning':
                    this.showMRPWarning(data);
                    break;
                case 'mrp_expired':
                    this.handleMRPExpired(data);
                    break;
                case 'round_ended':
                    this.handleRoundEnded(data);
                    break;
                case 'voting_started':
                    this.handleVotingStarted(data);
                    break;
                case 'discussion_archived':
                    this.handleDiscussionArchived(data);
                    break;
                case 'next_round_started':
                    this.handleNextRoundStarted(data);
                    break;
                default:
                    console.log('Unknown message type:', data.type);
            }
        } catch (error) {
            console.error('Error processing WebSocket message:', error);
        }
    }
    
    onError(error) {
        console.error('WebSocket error:', error);
        
        // Show error indicator
        const indicator = document.getElementById('ws-status');
        if (indicator) {
            indicator.className = 'ws-status error';
            indicator.title = 'Connection error';
        }
    }
    
    onClose() {
        console.log('WebSocket disconnected');
        
        // Show disconnected indicator
        const indicator = document.getElementById('ws-status');
        if (indicator) {
            indicator.className = 'ws-status disconnected';
            indicator.title = 'Disconnected - attempting to reconnect...';
        }
        
        this.scheduleReconnect();
    }
    
    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`Reconnecting in ${this.reconnectDelay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
            setTimeout(() => this.connect(), this.reconnectDelay);
        } else {
            console.error('Max reconnection attempts reached');
            showToast('Lost connection to server. Please refresh the page.', 'error');
        }
    }
    
    updateMRPTimer(data) {
        const timerElement = document.getElementById('mrp-timer');
        if (timerElement) {
            const minutes = Math.floor(data.time_remaining_seconds / 60);
            const seconds = data.time_remaining_seconds % 60;
            timerElement.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
            
            // Update global timer state for client-side fallback
            if (window.mrpTimerState) {
                window.mrpTimerState.serverTimeRemaining = data.time_remaining_seconds;
                window.mrpTimerState.lastUpdate = Date.now();
            }
            
            // Change color based on time remaining
            if (data.time_remaining_seconds < 300) { // < 5 minutes
                timerElement.className = 'timer-value critical';
            } else if (data.time_remaining_seconds < 600) { // < 10 minutes
                timerElement.className = 'timer-value warning';
            } else {
                timerElement.className = 'timer-value';
            }
        }
    }
    
    handleNewResponse(data) {
        showToast(`New response from ${data.author}`, 'info');
        
        // Reload response list if on discussion page
        const responseList = document.getElementById('response-list');
        if (responseList && typeof htmx !== 'undefined') {
            htmx.ajax('GET', `/discussions/${this.discussionId}/responses/`, {
                target: '#response-list',
                swap: 'innerHTML'
            });
        } else {
            // Fallback: reload page
            setTimeout(() => window.location.reload(), 1000);
        }
        
        // Update response count
        const countElement = document.getElementById('response-count');
        if (countElement && data.response_number) {
            countElement.textContent = data.response_number;
        }
    }
    
    showMRPWarning(data) {
        const percentage = data.percentage_remaining;
        let urgency = 'warning';
        
        if (percentage <= 5) {
            urgency = 'critical';
        } else if (percentage <= 10) {
            urgency = 'warning';
        }
        
        showToast(
            `MRP Warning: ${percentage}% time remaining (${Math.round(data.time_remaining_minutes)} minutes)`,
            urgency
        );
    }
    
    handleMRPExpired(data) {
        showToast('MRP has expired. Non-responders moved to observer status.', 'warning');
        setTimeout(() => window.location.reload(), 2000);
    }
    
    handleRoundEnded(data) {
        showToast(`Round ${data.round_number} has ended. ${data.reason}`, 'info');
        setTimeout(() => window.location.reload(), 2000);
    }
    
    handleVotingStarted(data) {
        showToast(`Voting window opened for Round ${data.round_number}`, 'info');
        setTimeout(() => window.location.reload(), 1000);
    }
    
    handleDiscussionArchived(data) {
        showToast(`Discussion archived: ${data.reason}`, 'info');
        setTimeout(() => window.location.href = '/discussions/', 3000);
    }
    
    handleNextRoundStarted(data) {
        showToast(`Round ${data.round_number} has started!`, 'success');
        setTimeout(() => window.location.reload(), 1000);
    }
    
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}


class NotificationWebSocket {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 3000;
        this.connect();
    }
    
    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/notifications/`;
        
        try {
            this.ws = new WebSocket(wsUrl);
            this.ws.onopen = () => this.onOpen();
            this.ws.onmessage = (e) => this.onMessage(e);
            this.ws.onerror = (e) => this.onError(e);
            this.ws.onclose = () => this.onClose();
        } catch (error) {
            console.error('Notification WebSocket error:', error);
            this.scheduleReconnect();
        }
    }
    
    onOpen() {
        console.log('Notification WebSocket connected');
        this.reconnectAttempts = 0;
    }
    
    onMessage(event) {
        try {
            const data = JSON.parse(event.data);
            console.log('Notification received:', data);
            
            if (data.type === 'notification') {
                this.handleNotification(data);
            }
        } catch (error) {
            console.error('Error processing notification:', error);
        }
    }
    
    onError(error) {
        console.error('Notification WebSocket error:', error);
    }
    
    onClose() {
        console.log('Notification WebSocket disconnected');
        this.scheduleReconnect();
    }
    
    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            setTimeout(() => this.connect(), this.reconnectDelay);
        }
    }
    
    handleNotification(data) {
        // Update notification bell badge
        const badge = document.getElementById('notification-badge');
        if (badge) {
            const currentCount = parseInt(badge.textContent) || 0;
            badge.textContent = currentCount + 1;
            badge.style.display = 'inline';
        }
        
        // Show toast
        const type = data.is_critical ? 'warning' : 'info';
        showToast(data.message || data.title || 'New notification', type);
        
        // Play sound for critical notifications
        if (data.is_critical && window.notificationSound) {
            window.notificationSound.play().catch(e => console.log('Could not play sound:', e));
        }
    }
    
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}


// Toast notification helper
function showToast(message, type = 'info') {
    // Remove existing toasts
    const existingToasts = document.querySelectorAll('.toast');
    existingToasts.forEach(toast => toast.remove());
    
    // Create new toast
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    // Add icon based on type
    const icons = {
        'success': '✓',
        'info': 'ℹ',
        'warning': '⚠',
        'error': '✕',
        'critical': '⚠'
    };
    
    const icon = icons[type] || 'ℹ';
    toast.innerHTML = `<span class="toast-icon">${icon}</span><span class="toast-message">${message}</span>`;
    
    document.body.appendChild(toast);
    
    // Animate in
    setTimeout(() => toast.classList.add('show'), 10);
    
    // Auto-remove after 5 seconds (critical stays longer)
    const duration = type === 'critical' ? 10000 : 5000;
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}


// Initialize WebSockets on page load
document.addEventListener('DOMContentLoaded', function() {
    // Initialize notification WebSocket for all authenticated users
    if (document.body.dataset.authenticated === 'true') {
        window.notificationWS = new NotificationWebSocket();
    }
    
    // Initialize discussion WebSocket if on a discussion page
    const discussionId = document.body.dataset.discussionId;
    if (discussionId) {
        window.discussionWS = new DiscussionWebSocket(discussionId);
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    if (window.notificationWS) {
        window.notificationWS.disconnect();
    }
    if (window.discussionWS) {
        window.discussionWS.disconnect();
    }
});
