// SeeSee — Alpine.js components, keyboard shortcuts, relative timestamps

// ---------------------------------------------------------------------------
// Toast notification manager
// ---------------------------------------------------------------------------
function toastManager() {
    return {
        toasts: [],
        _counter: 0,
        addToast(detail) {
            const id = ++this._counter;
            const toast = { id, message: detail.message, type: detail.type || 'success', visible: true };
            this.toasts.push(toast);
            setTimeout(() => this.removeToast(id), 4000);
        },
        removeToast(id) {
            const toast = this.toasts.find(t => t.id === id);
            if (toast) toast.visible = false;
            setTimeout(() => { this.toasts = this.toasts.filter(t => t.id !== id); }, 300);
        }
    };
}

// Helper to dispatch toast events from anywhere
function showToast(message, type) {
    window.dispatchEvent(new CustomEvent('toast', { detail: { message, type: type || 'success' } }));
}

// ---------------------------------------------------------------------------
// Keyboard shortcuts (/, j, k, Enter, Esc)
// ---------------------------------------------------------------------------
document.addEventListener('keydown', function(e) {
    const tag = document.activeElement.tagName;
    const isTyping = ['INPUT', 'TEXTAREA', 'SELECT'].includes(tag);

    // / — focus search (global, prevent typing / into the input)
    if (e.key === '/' && !isTyping) {
        const searchInput = document.querySelector('input[name="q"]');
        if (searchInput) {
            e.preventDefault();
            searchInput.focus();
            searchInput.select();
        }
        return;
    }

    // Esc — blur inputs, close modals
    if (e.key === 'Escape') {
        if (isTyping) {
            document.activeElement.blur();
            return;
        }
        return;
    }

    // j/k/Enter — only work when not typing and on pages with navigable rows
    if (isTyping) return;

    const rows = document.querySelectorAll('tbody tr[data-href]');
    if (rows.length === 0) return;

    const highlighted = document.querySelector('tbody tr.keyboard-highlight');
    let currentIdx = -1;
    if (highlighted) {
        rows.forEach((row, i) => { if (row === highlighted) currentIdx = i; });
    }

    if (e.key === 'j') {
        e.preventDefault();
        const nextIdx = Math.min(currentIdx + 1, rows.length - 1);
        _highlightRow(rows, nextIdx);
    } else if (e.key === 'k') {
        e.preventDefault();
        const prevIdx = Math.max(currentIdx - 1, 0);
        _highlightRow(rows, prevIdx);
    } else if (e.key === 'Enter' && highlighted) {
        e.preventDefault();
        const href = highlighted.getAttribute('data-href');
        if (href) window.location = href;
    }
});

function _highlightRow(rows, idx) {
    rows.forEach(row => {
        row.classList.remove('keyboard-highlight', 'ring-2', 'ring-inset', 'ring-mint/50');
    });
    if (idx >= 0 && idx < rows.length) {
        const row = rows[idx];
        row.classList.add('keyboard-highlight', 'ring-2', 'ring-inset', 'ring-mint/50');
        row.scrollIntoView({ block: 'nearest' });
    }
}

// ---------------------------------------------------------------------------
// Relative timestamps
// ---------------------------------------------------------------------------
function relativeTime(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString.endsWith('Z') ? isoString : isoString + 'Z');
    const now = new Date();
    const diffMs = now - date;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHr = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHr / 24);

    if (diffSec < 60) return 'just now';
    if (diffMin < 60) return diffMin + ' minute' + (diffMin === 1 ? '' : 's') + ' ago';
    if (diffHr < 24) return diffHr + ' hour' + (diffHr === 1 ? '' : 's') + ' ago';
    if (diffDay === 1) return 'yesterday';
    if (diffDay < 30) return diffDay + ' day' + (diffDay === 1 ? '' : 's') + ' ago';

    // Fall back to short date
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return months[date.getMonth()] + ' ' + date.getDate();
}

function updateRelativeTimes() {
    document.querySelectorAll('[data-timestamp]').forEach(function(el) {
        const iso = el.getAttribute('data-timestamp');
        el.textContent = relativeTime(iso);
        el.setAttribute('title', iso.replace('T', ' ').substring(0, 19));
    });
}

// Run on load and every 30 seconds
document.addEventListener('DOMContentLoaded', function() {
    updateRelativeTimes();
    setInterval(updateRelativeTimes, 30000);
});

// Also run when Alpine.js has initialized (for dynamic content)
document.addEventListener('alpine:init', function() {
    setTimeout(updateRelativeTimes, 100);
});

// Flash message → toast bridge: detect query params and fire toasts
// Note: credentials (created, rotated_key) use server-side flash cookies
// and fire toasts via inline <script> tags in templates instead.
document.addEventListener('DOMContentLoaded', function() {
    const params = new URLSearchParams(window.location.search);
    if (params.has('purged')) {
        showToast('All emails purged');
    }
    if (params.has('deleted')) {
        showToast('Email deleted');
    }
    if (params.has('cleanup')) {
        showToast('Cleanup completed');
    }
});
