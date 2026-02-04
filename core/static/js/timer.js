/**
 * Timer
 * 
 * Countdown timer for MRP (Minimum Response Period) and other time-based features.
 * Displays time remaining and updates in real-time.
 */

(function() {
    'use strict';
    
    /**
     * Format time duration
     * @param {number} seconds - Total seconds
     * @returns {string} - Formatted time string
     */
    function formatTime(seconds) {
        if (seconds <= 0) {
            return 'Expired';
        }
        
        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        
        const parts = [];
        
        if (days > 0) {
            parts.push(`${days}d`);
        }
        if (hours > 0 || days > 0) {
            parts.push(`${hours}h`);
        }
        if (minutes > 0 || hours > 0 || days > 0) {
            parts.push(`${minutes}m`);
        }
        parts.push(`${secs}s`);
        
        return parts.join(' ');
    }
    
    /**
     * Calculate seconds remaining
     * @param {Date|string} endTime - End time
     * @returns {number} - Seconds remaining
     */
    function getSecondsRemaining(endTime) {
        const end = new Date(endTime);
        const now = new Date();
        return Math.max(0, Math.floor((end - now) / 1000));
    }
    
    /**
     * Timer class
     */
    class Timer {
        constructor(element) {
            this.element = element;
            this.endTime = element.getAttribute('data-end-time');
            this.warningThreshold = parseInt(element.getAttribute('data-warning-seconds') || '3600', 10); // 1 hour default
            this.urgentThreshold = parseInt(element.getAttribute('data-urgent-seconds') || '600', 10); // 10 minutes default
            this.onExpire = element.getAttribute('data-on-expire');
            this.interval = null;
            
            if (!this.endTime) {
                console.error('Timer: data-end-time attribute is required');
                return;
            }
            
            this.start();
        }
        
        start() {
            this.update();
            this.interval = setInterval(() => this.update(), 1000);
        }
        
        stop() {
            if (this.interval) {
                clearInterval(this.interval);
                this.interval = null;
            }
        }
        
        update() {
            const secondsRemaining = getSecondsRemaining(this.endTime);
            const timeString = formatTime(secondsRemaining);
            
            // Update display
            this.element.textContent = timeString;
            
            // Update classes based on time remaining
            this.element.classList.remove('urgent', 'warning');
            
            if (secondsRemaining <= 0) {
                this.element.classList.add('urgent');
                this.handleExpiration();
            } else if (secondsRemaining <= this.urgentThreshold) {
                this.element.classList.add('urgent');
            } else if (secondsRemaining <= this.warningThreshold) {
                this.element.classList.add('warning');
            }
        }
        
        handleExpiration() {
            this.stop();
            
            if (this.onExpire) {
                if (this.onExpire === 'reload') {
                    window.location.reload();
                } else if (this.onExpire.startsWith('redirect:')) {
                    const url = this.onExpire.substring(9);
                    window.location.href = url;
                } else if (this.onExpire.startsWith('function:')) {
                    const functionName = this.onExpire.substring(9);
                    if (typeof window[functionName] === 'function') {
                        window[functionName]();
                    }
                } else if (this.onExpire.startsWith('htmx:')) {
                    // Trigger HTMX request
                    const url = this.onExpire.substring(5);
                    if (typeof htmx !== 'undefined') {
                        htmx.ajax('GET', url, {target: 'body'});
                    }
                }
            }
            
            // Dispatch custom event
            this.element.dispatchEvent(new CustomEvent('timer:expired', {
                detail: { endTime: this.endTime },
                bubbles: true
            }));
        }
    }
    
    /**
     * Initialize all timers on the page
     */
    function initAll() {
        const timerElements = document.querySelectorAll('[data-timer]');
        
        timerElements.forEach(function(element) {
            // Skip if already initialized
            if (element.dataset.timerInitialized === 'true') {
                return;
            }
            
            const timer = new Timer(element);
            
            // Store timer instance
            element.timerInstance = timer;
            element.dataset.timerInitialized = 'true';
        });
    }
    
    /**
     * Stop all timers
     */
    function stopAll() {
        const timerElements = document.querySelectorAll('[data-timer]');
        
        timerElements.forEach(function(element) {
            if (element.timerInstance) {
                element.timerInstance.stop();
                element.timerInstance = null;
                element.dataset.timerInitialized = 'false';
            }
        });
    }
    
    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
    
    // Re-initialize when HTMX swaps content
    if (typeof htmx !== 'undefined') {
        document.body.addEventListener('htmx:beforeSwap', function() {
            stopAll();
        });
        
        document.body.addEventListener('htmx:afterSwap', function() {
            initAll();
        });
    }
    
    // Clean up on page unload
    window.addEventListener('beforeunload', function() {
        stopAll();
    });
    
    // Export for manual use
    window.Timer = {
        init: initAll,
        stop: stopAll,
        formatTime: formatTime,
        getSecondsRemaining: getSecondsRemaining
    };
})();
