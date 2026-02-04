/**
 * Modal
 * 
 * Modal dialog management with backdrop, keyboard navigation, and accessibility.
 * Supports confirmation dialogs, forms, and custom content.
 */

(function() {
    'use strict';
    
    /**
     * Modal class
     */
    class Modal {
        constructor(id) {
            this.id = id;
            this.modal = document.getElementById(id);
            
            if (!this.modal) {
                console.error(`Modal: Element with id "${id}" not found`);
                return;
            }
            
            this.backdrop = null;
            this.isOpen = false;
            this.focusedElementBeforeOpen = null;
            
            this.init();
        }
        
        init() {
            // Create backdrop if it doesn't exist
            if (!this.modal.querySelector('.modal-backdrop')) {
                this.backdrop = document.createElement('div');
                this.backdrop.className = 'modal-backdrop';
                this.backdrop.setAttribute('aria-hidden', 'true');
                this.modal.insertBefore(this.backdrop, this.modal.firstChild);
                
                // Close on backdrop click
                this.backdrop.addEventListener('click', () => this.close());
            } else {
                this.backdrop = this.modal.querySelector('.modal-backdrop');
            }
            
            // Set up event listeners
            this.setupEventListeners();
            
            // Initially hide modal
            this.modal.classList.add('hidden');
        }
        
        setupEventListeners() {
            // Close button
            const closeButtons = this.modal.querySelectorAll('[data-modal-close]');
            closeButtons.forEach(button => {
                button.addEventListener('click', () => this.close());
            });
            
            // ESC key to close
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && this.isOpen) {
                    this.close();
                }
            });
            
            // Confirm button
            const confirmButton = this.modal.querySelector('[data-modal-confirm]');
            if (confirmButton) {
                confirmButton.addEventListener('click', () => this.confirm());
            }
        }
        
        open() {
            // Store currently focused element
            this.focusedElementBeforeOpen = document.activeElement;
            
            // Show modal
            this.modal.classList.remove('hidden');
            this.modal.setAttribute('aria-hidden', 'false');
            
            // Prevent body scroll
            document.body.style.overflow = 'hidden';
            
            // Focus first focusable element in modal
            const focusableElements = this.modal.querySelectorAll(
                'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
            );
            if (focusableElements.length > 0) {
                focusableElements[0].focus();
            }
            
            this.isOpen = true;
            
            // Dispatch event
            this.modal.dispatchEvent(new CustomEvent('modal:opened', {
                detail: { modalId: this.id },
                bubbles: true
            }));
        }
        
        close() {
            // Hide modal
            this.modal.classList.add('hidden');
            this.modal.setAttribute('aria-hidden', 'true');
            
            // Restore body scroll
            document.body.style.overflow = '';
            
            // Restore focus
            if (this.focusedElementBeforeOpen) {
                this.focusedElementBeforeOpen.focus();
            }
            
            this.isOpen = false;
            
            // Dispatch event
            this.modal.dispatchEvent(new CustomEvent('modal:closed', {
                detail: { modalId: this.id },
                bubbles: true
            }));
        }
        
        confirm() {
            // Get confirmation callback
            const onConfirm = this.modal.getAttribute('data-on-confirm');
            
            if (onConfirm) {
                if (onConfirm.startsWith('function:')) {
                    const functionName = onConfirm.substring(9);
                    if (typeof window[functionName] === 'function') {
                        window[functionName]();
                    }
                } else if (onConfirm.startsWith('htmx:')) {
                    // Trigger HTMX request
                    const url = onConfirm.substring(5);
                    if (typeof htmx !== 'undefined') {
                        htmx.ajax('POST', url, {target: 'body'});
                    }
                } else if (onConfirm.startsWith('submit:')) {
                    // Submit form
                    const formId = onConfirm.substring(7);
                    const form = document.getElementById(formId);
                    if (form) {
                        form.submit();
                    }
                }
            }
            
            // Dispatch event
            this.modal.dispatchEvent(new CustomEvent('modal:confirmed', {
                detail: { modalId: this.id },
                bubbles: true
            }));
            
            this.close();
        }
        
        setTitle(title) {
            const titleElement = this.modal.querySelector('[data-modal-title]');
            if (titleElement) {
                titleElement.textContent = title;
            }
        }
        
        setContent(content) {
            const contentElement = this.modal.querySelector('[data-modal-content]');
            if (contentElement) {
                if (typeof content === 'string') {
                    contentElement.innerHTML = content;
                } else {
                    contentElement.innerHTML = '';
                    contentElement.appendChild(content);
                }
            }
        }
    }
    
    /**
     * Modal registry
     */
    const modals = {};
    
    /**
     * Get or create modal instance
     * @param {string} id - Modal element ID
     * @returns {Modal} - Modal instance
     */
    function getModal(id) {
        if (!modals[id]) {
            modals[id] = new Modal(id);
        }
        return modals[id];
    }
    
    /**
     * Open modal by ID
     * @param {string} id - Modal element ID
     */
    function openModal(id) {
        const modal = getModal(id);
        if (modal) {
            modal.open();
        }
    }
    
    /**
     * Close modal by ID
     * @param {string} id - Modal element ID
     */
    function closeModal(id) {
        const modal = modals[id];
        if (modal) {
            modal.close();
        }
    }
    
    /**
     * Show confirmation dialog
     * @param {Object} options - Configuration options
     * @returns {Promise} - Resolves on confirm, rejects on cancel
     */
    function confirm(options) {
        return new Promise((resolve, reject) => {
            const {
                title = 'Confirm',
                message = 'Are you sure?',
                confirmText = 'Confirm',
                cancelText = 'Cancel',
                confirmClass = 'btn-danger',
                modalId = 'confirmation-modal'
            } = options;
            
            // Create or get modal
            let modal = document.getElementById(modalId);
            
            if (!modal) {
                modal = document.createElement('div');
                modal.id = modalId;
                modal.className = 'fixed inset-0 z-50 hidden';
                modal.innerHTML = `
                    <div class="modal-backdrop"></div>
                    <div class="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0">
                        <div class="modal-panel">
                            <div class="bg-white px-4 pb-4 pt-5 sm:p-6 sm:pb-4">
                                <div class="sm:flex sm:items-start">
                                    <div class="mx-auto flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full bg-red-100 sm:mx-0 sm:h-10 sm:w-10">
                                        <svg class="h-6 w-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                                            <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                                        </svg>
                                    </div>
                                    <div class="mt-3 text-center sm:ml-4 sm:mt-0 sm:text-left">
                                        <h3 class="text-base font-semibold leading-6 text-gray-900" data-modal-title></h3>
                                        <div class="mt-2">
                                            <p class="text-sm text-gray-500" data-modal-content></p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="bg-gray-50 px-4 py-3 sm:flex sm:flex-row-reverse sm:px-6">
                                <button type="button" data-modal-confirm class="inline-flex w-full justify-center rounded-md px-3 py-2 text-sm font-semibold text-white shadow-sm sm:ml-3 sm:w-auto"></button>
                                <button type="button" data-modal-close class="mt-3 inline-flex w-full justify-center rounded-md bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50 sm:mt-0 sm:w-auto"></button>
                            </div>
                        </div>
                    </div>
                `;
                document.body.appendChild(modal);
            }
            
            const modalInstance = getModal(modalId);
            
            // Set content
            modalInstance.setTitle(title);
            modalInstance.setContent(message);
            
            const confirmButton = modal.querySelector('[data-modal-confirm]');
            const cancelButton = modal.querySelector('[data-modal-close]');
            
            confirmButton.textContent = confirmText;
            confirmButton.className = `inline-flex w-full justify-center rounded-md px-3 py-2 text-sm font-semibold text-white shadow-sm sm:ml-3 sm:w-auto ${confirmClass}`;
            
            cancelButton.textContent = cancelText;
            
            // Set up one-time event listeners
            const handleConfirm = () => {
                modal.removeEventListener('modal:confirmed', handleConfirm);
                modal.removeEventListener('modal:closed', handleCancel);
                resolve(true);
            };
            
            const handleCancel = () => {
                modal.removeEventListener('modal:confirmed', handleConfirm);
                modal.removeEventListener('modal:closed', handleCancel);
                reject(false);
            };
            
            modal.addEventListener('modal:confirmed', handleConfirm);
            modal.addEventListener('modal:closed', handleCancel);
            
            // Open modal
            modalInstance.open();
        });
    }
    
    /**
     * Initialize all modals on the page
     */
    function initAll() {
        // Initialize modal triggers
        document.querySelectorAll('[data-modal-open]').forEach(trigger => {
            trigger.addEventListener('click', function(e) {
                e.preventDefault();
                const modalId = this.getAttribute('data-modal-open');
                openModal(modalId);
            });
        });
        
        // Initialize all modal elements
        document.querySelectorAll('[data-modal]').forEach(element => {
            const modalId = element.id;
            if (modalId) {
                getModal(modalId);
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
    
    // Export for global use
    window.Modal = {
        open: openModal,
        close: closeModal,
        confirm: confirm,
        getModal: getModal,
        init: initAll
    };
})();
