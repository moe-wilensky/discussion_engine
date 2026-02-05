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
                case 'voting_updated':
                    this.handleVotingUpdated(data);
                    break;
                case 'voting_closed':
                    this.handleVotingClosed(data);
                    break;
                case 'parameter_changed':
                    this.handleParameterChanged(data);
                    break;
                case 'user_removed':
                    this.handleUserRemoved(data);
                    break;
                case 'new_participant':
                    this.handleNewParticipant(data);
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
        console.log('MRP timer update:', data);
        const timerElement = document.getElementById('mrp-timer');
        if (timerElement) {
            const timeRemaining = Math.max(0, data.time_remaining_seconds);
            const minutes = Math.floor(timeRemaining / 60);
            const seconds = timeRemaining % 60;
            timerElement.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;

            // Update global timer state for client-side fallback
            if (window.mrpTimerState) {
                window.mrpTimerState.serverTimeRemaining = timeRemaining;
                window.mrpTimerState.lastUpdate = Date.now();
            }

            // Handle timer reaching zero
            if (timeRemaining <= 0) {
                console.log('MRP timer expired - triggering reload');
                timerElement.className = 'timer-value expired';
                timerElement.textContent = '0:00';
                showToast('MRP has expired', 'warning');
                // Reload page after short delay to show updated state
                setTimeout(() => window.location.reload(), 2000);
                return;
            }

            // Change color based on time remaining
            if (timeRemaining < 300) { // < 5 minutes
                timerElement.className = 'timer-value critical';
            } else if (timeRemaining < 600) { // < 10 minutes
                timerElement.className = 'timer-value warning';
            } else {
                timerElement.className = 'timer-value';
            }
        }
    }
    
    handleNewResponse(data) {
        console.log('New response received:', data);
        showToast(`New response from ${data.author}`, 'info');

        // Reload response list if on discussion page
        const responseList = document.getElementById('response-list');
        if (responseList && typeof htmx !== 'undefined' && data.round_number) {
            // Use correct API endpoint with round number
            const apiUrl = `/api/discussions/${this.discussionId}/rounds/${data.round_number}/responses/`;
            console.log('Reloading responses from:', apiUrl);
            htmx.ajax('GET', apiUrl, {
                target: '#response-list',
                swap: 'innerHTML'
            });
        } else {
            // Fallback: reload page if round number not available
            console.log('Round number not available, reloading page');
            setTimeout(() => window.location.reload(), 1000);
        }

        // Update response count
        const countElement = document.getElementById('response-count');
        if (countElement && data.response_number) {
            countElement.textContent = data.response_number;
        }

        // Update MRP timer if MRP was updated
        if (data.mrp_updated && data.new_mrp_deadline) {
            console.log('MRP updated:', {
                new_mrp_minutes: data.new_mrp_minutes,
                new_mrp_deadline: data.new_mrp_deadline
            });
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

    handleVotingUpdated(data) {
        console.log('Voting updated:', data);
        const parameterName = data.parameter === 'mrl' ? 'MRL' :
                             data.parameter === 'rtm' ? 'RTM' :
                             data.parameter;
        showToast(`Vote cast for ${parameterName} (${data.votes_cast} total votes)`, 'info');

        // Update vote count display if element exists
        const voteCountElement = document.getElementById(`${data.parameter}-vote-count`);
        if (voteCountElement) {
            voteCountElement.textContent = data.votes_cast;
        }
    }

    handleVotingClosed(data) {
        console.log('Voting closed:', data);
        let message = `Voting closed for Round ${data.round_number}`;

        if (data.mrl_result) {
            message += ` | MRL: ${data.mrl_result}`;
        }
        if (data.rtm_result) {
            message += ` | RTM: ${data.rtm_result}`;
        }
        if (data.users_removed && data.users_removed.length > 0) {
            message += ` | ${data.users_removed.length} user(s) removed`;
        }

        showToast(message, 'warning');
        setTimeout(() => window.location.reload(), 2000);
    }

    handleParameterChanged(data) {
        console.log('Parameter changed:', data);
        const parameterName = data.parameter === 'mrl' ? 'MRL' : 'RTM';
        showToast(`${parameterName} changed from ${data.old_value} to ${data.new_value}`, 'info');

        // Update parameter display if element exists
        const paramElement = document.getElementById(`${data.parameter}-value`);
        if (paramElement) {
            paramElement.textContent = data.new_value;
            // Add animation to highlight the change
            paramElement.classList.add('parameter-updated');
            setTimeout(() => paramElement.classList.remove('parameter-updated'), 2000);
        }
    }

    handleUserRemoved(data) {
        console.log('User removed:', data);
        const username = data.username || 'A user';
        const reason = data.reason === 'vote_based_removal' ? 'by vote' : data.reason;
        showToast(`${username} was removed from the discussion (${reason})`, 'warning');

        // If the current user was removed, reload to show observer UI
        const currentUsername = document.body.dataset.username;
        if (currentUsername === data.username) {
            showToast('You have been moved to observer status', 'warning');
            setTimeout(() => window.location.reload(), 2000);
        } else {
            // Reload to update participant list
            setTimeout(() => window.location.reload(), 2000);
        }
    }

    handleNewParticipant(data) {
        console.log('New participant:', data);
        const username = data.username || 'A user';
        const message = data.rejoined ?
            `${username} has rejoined the discussion` :
            `${username} joined the discussion`;

        showToast(message, 'info');

        // If the current user rejoined, reload to show active UI
        const currentUsername = document.body.dataset.username;
        if (currentUsername === data.username && data.rejoined) {
            showToast('You have successfully rejoined the discussion!', 'success');
            setTimeout(() => window.location.reload(), 1500);
        } else {
            // Reload to update participant list
            setTimeout(() => window.location.reload(), 2000);
        }
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
