/**
 * Character Counter
 * 
 * Provides real-time character counting for textareas with visual feedback.
 * Updates counter display and applies warning/danger states based on limits.
 */

(function() {
    'use strict';
    
    /**
     * Initialize character counter for a textarea
     * @param {HTMLTextAreaElement} textarea - The textarea element
     * @param {HTMLElement} counter - The counter display element
     * @param {number} maxLength - Maximum character limit
     */
    function initCharacterCounter(textarea, counter, maxLength) {
        if (!textarea || !counter) return;
        
        function updateCounter() {
            const currentLength = textarea.value.length;
            const remaining = maxLength - currentLength;
            
            // Update counter text
            counter.textContent = `${currentLength} / ${maxLength} characters`;
            
            // Remove all state classes
            counter.classList.remove('warning', 'danger', 'text-gray-600', 'text-amber-600', 'text-red-600');
            
            // Apply appropriate state class
            if (currentLength > maxLength) {
                counter.classList.add('danger', 'text-red-600');
                counter.textContent += ` (${Math.abs(remaining)} over limit)`;
            } else if (remaining < maxLength * 0.1) { // Warning at 90% capacity
                counter.classList.add('warning', 'text-amber-600');
            } else {
                counter.classList.add('text-gray-600');
            }
            
            // Enable/disable submit button if it exists
            const form = textarea.closest('form');
            if (form) {
                const submitButton = form.querySelector('button[type="submit"]');
                if (submitButton) {
                    submitButton.disabled = currentLength > maxLength || currentLength === 0;
                }
            }
        }
        
        // Update on input
        textarea.addEventListener('input', updateCounter);
        
        // Update on paste
        textarea.addEventListener('paste', function() {
            setTimeout(updateCounter, 10);
        });
        
        // Initial update
        updateCounter();
    }
    
    /**
     * Initialize all character counters on the page
     */
    function initAll() {
        // Find all textareas with data-counter attribute
        const textareas = document.querySelectorAll('textarea[data-counter]');
        
        textareas.forEach(function(textarea) {
            const counterId = textarea.getAttribute('data-counter');
            const counter = document.getElementById(counterId);
            const maxLength = parseInt(textarea.getAttribute('maxlength') || textarea.getAttribute('data-max-length'), 10);
            
            if (counter && maxLength) {
                initCharacterCounter(textarea, counter, maxLength);
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
        document.body.addEventListener('htmx:afterSwap', initAll);
    }
    
    // Export for manual initialization
    window.CharacterCounter = {
        init: initCharacterCounter,
        initAll: initAll
    };
})();
