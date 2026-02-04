/**
 * Form Validation
 * 
 * Client-side form validation with real-time feedback.
 * Validates inputs, displays error messages, and prevents invalid submissions.
 */

(function() {
    'use strict';
    
    /**
     * Validation rules
     */
    const validationRules = {
        required: function(value) {
            return value.trim().length > 0;
        },
        
        email: function(value) {
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            return emailRegex.test(value);
        },
        
        phone: function(value) {
            // E.164 format: +[country code][number]
            const phoneRegex = /^\+[1-9]\d{1,14}$/;
            return phoneRegex.test(value);
        },
        
        minLength: function(value, min) {
            return value.length >= min;
        },
        
        maxLength: function(value, max) {
            return value.length <= max;
        },
        
        numeric: function(value) {
            return /^\d+$/.test(value);
        },
        
        alphanumeric: function(value) {
            return /^[a-zA-Z0-9]+$/.test(value);
        },
        
        url: function(value) {
            try {
                new URL(value);
                return true;
            } catch {
                return false;
            }
        }
    };
    
    /**
     * Error messages
     */
    const errorMessages = {
        required: 'This field is required.',
        email: 'Please enter a valid email address.',
        phone: 'Please enter a valid phone number (e.g., +1234567890).',
        minLength: 'Minimum length is {min} characters.',
        maxLength: 'Maximum length is {max} characters.',
        numeric: 'Please enter numbers only.',
        alphanumeric: 'Please enter letters and numbers only.',
        url: 'Please enter a valid URL.'
    };
    
    /**
     * Validate a single field
     * @param {HTMLElement} field - The input/textarea/select element
     * @returns {boolean} - True if valid, false otherwise
     */
    function validateField(field) {
        const value = field.value;
        const rules = field.getAttribute('data-validate');
        
        if (!rules) return true;
        
        const ruleList = rules.split(' ');
        let isValid = true;
        let errorMessage = '';
        
        for (const rule of ruleList) {
            const [ruleName, ruleParam] = rule.split(':');
            
            if (ruleName === 'required' && !validationRules.required(value)) {
                isValid = false;
                errorMessage = errorMessages.required;
                break;
            }
            
            // Skip other validations if field is empty and not required
            if (value.trim().length === 0) continue;
            
            if (ruleName === 'email' && !validationRules.email(value)) {
                isValid = false;
                errorMessage = errorMessages.email;
                break;
            }
            
            if (ruleName === 'phone' && !validationRules.phone(value)) {
                isValid = false;
                errorMessage = errorMessages.phone;
                break;
            }
            
            if (ruleName === 'minLength') {
                const min = parseInt(ruleParam, 10);
                if (!validationRules.minLength(value, min)) {
                    isValid = false;
                    errorMessage = errorMessages.minLength.replace('{min}', min);
                    break;
                }
            }
            
            if (ruleName === 'maxLength') {
                const max = parseInt(ruleParam, 10);
                if (!validationRules.maxLength(value, max)) {
                    isValid = false;
                    errorMessage = errorMessages.maxLength.replace('{max}', max);
                    break;
                }
            }
            
            if (ruleName === 'numeric' && !validationRules.numeric(value)) {
                isValid = false;
                errorMessage = errorMessages.numeric;
                break;
            }
            
            if (ruleName === 'alphanumeric' && !validationRules.alphanumeric(value)) {
                isValid = false;
                errorMessage = errorMessages.alphanumeric;
                break;
            }
            
            if (ruleName === 'url' && !validationRules.url(value)) {
                isValid = false;
                errorMessage = errorMessages.url;
                break;
            }
        }
        
        // Update UI
        updateFieldUI(field, isValid, errorMessage);
        
        return isValid;
    }
    
    /**
     * Update field UI based on validation state
     * @param {HTMLElement} field - The input element
     * @param {boolean} isValid - Whether the field is valid
     * @param {string} errorMessage - The error message to display
     */
    function updateFieldUI(field, isValid, errorMessage) {
        const container = field.closest('.form-group, .mb-4, .space-y-1');
        if (!container) return;
        
        // Remove existing error
        const existingError = container.querySelector('.form-error');
        if (existingError) {
            existingError.remove();
        }
        
        // Remove error classes
        field.classList.remove('border-red-500', 'focus:border-red-500', 'focus:ring-red-500');
        
        if (!isValid) {
            // Add error classes
            field.classList.add('border-red-500', 'focus:border-red-500', 'focus:ring-red-500');
            
            // Add error message
            const errorDiv = document.createElement('div');
            errorDiv.className = 'form-error text-red-600 text-sm mt-1';
            errorDiv.textContent = errorMessage;
            
            // Insert after field
            field.parentNode.insertBefore(errorDiv, field.nextSibling);
        } else {
            // Add success classes if field has value
            if (field.value.trim().length > 0) {
                field.classList.remove('border-gray-300');
                field.classList.add('border-green-500');
            }
        }
    }
    
    /**
     * Validate entire form
     * @param {HTMLFormElement} form - The form element
     * @returns {boolean} - True if all fields are valid
     */
    function validateForm(form) {
        const fields = form.querySelectorAll('[data-validate]');
        let isValid = true;
        
        fields.forEach(function(field) {
            if (!validateField(field)) {
                isValid = false;
            }
        });
        
        return isValid;
    }
    
    /**
     * Initialize form validation
     * @param {HTMLFormElement} form - The form element
     */
    function initForm(form) {
        // Real-time validation on blur
        form.querySelectorAll('[data-validate]').forEach(function(field) {
            field.addEventListener('blur', function() {
                validateField(field);
            });
            
            // Clear errors on input
            field.addEventListener('input', function() {
                const container = field.closest('.form-group, .mb-4, .space-y-1');
                if (container) {
                    const existingError = container.querySelector('.form-error');
                    if (existingError && field.value.trim().length > 0) {
                        validateField(field);
                    }
                }
            });
        });
        
        // Validate on submit
        form.addEventListener('submit', function(e) {
            if (!validateForm(form)) {
                e.preventDefault();
                e.stopPropagation();
                
                // Focus first invalid field
                const firstInvalid = form.querySelector('.border-red-500');
                if (firstInvalid) {
                    firstInvalid.focus();
                }
                
                // Show error toast
                if (window.Toast) {
                    window.Toast.show('Please fix the errors in the form.', 'error');
                }
                
                return false;
            }
        });
    }
    
    /**
     * Initialize all forms on the page
     */
    function initAll() {
        const forms = document.querySelectorAll('form[data-validate-form]');
        forms.forEach(initForm);
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
    
    // Export for manual use
    window.FormValidation = {
        validate: validateField,
        validateForm: validateForm,
        init: initForm,
        initAll: initAll
    };
})();
