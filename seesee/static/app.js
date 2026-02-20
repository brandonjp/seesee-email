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
// Click-to-copy helper
// ---------------------------------------------------------------------------
function copyToClipboard(text, buttonEl) {
    navigator.clipboard.writeText(text).then(function() {
        showToast('Copied to clipboard');
        if (buttonEl) {
            const icon = buttonEl.querySelector('.copy-icon');
            const check = buttonEl.querySelector('.check-icon');
            if (icon && check) {
                icon.classList.add('hidden');
                check.classList.remove('hidden');
                setTimeout(function() {
                    icon.classList.remove('hidden');
                    check.classList.add('hidden');
                }, 1500);
            }
        }
    });
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
// Relative timestamps — all stored timestamps are UTC
// ---------------------------------------------------------------------------
function _parseUtcTimestamp(isoString) {
    if (!isoString) return null;
    // Ensure the string is interpreted as UTC: append Z if no timezone indicator
    var s = isoString;
    if (!s.endsWith('Z') && !s.includes('+') && !/\d{2}:\d{2}$/.test(s.slice(-6))) {
        s = s + 'Z';
    }
    return new Date(s);
}

function relativeTime(isoString) {
    var date = _parseUtcTimestamp(isoString);
    if (!date || isNaN(date.getTime())) return '';
    var now = new Date();
    var diffMs = now - date;
    var diffSec = Math.floor(diffMs / 1000);
    var diffMin = Math.floor(diffSec / 60);
    var diffHr = Math.floor(diffMin / 60);
    var diffDay = Math.floor(diffHr / 24);

    if (diffSec < 60) return 'just now';
    if (diffMin < 60) return diffMin + ' minute' + (diffMin === 1 ? '' : 's') + ' ago';
    if (diffHr < 24) return diffHr + ' hour' + (diffHr === 1 ? '' : 's') + ' ago';
    if (diffDay === 1) return 'yesterday';
    if (diffDay < 30) return diffDay + ' day' + (diffDay === 1 ? '' : 's') + ' ago';

    // Fall back to short date in user's local timezone
    var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return months[date.getMonth()] + ' ' + date.getDate();
}

function _formatLocalDateTime(date) {
    // Format in the browser's local timezone with timezone label
    try {
        return date.toLocaleString(undefined, {
            month: 'short', day: 'numeric', year: 'numeric',
            hour: 'numeric', minute: '2-digit', timeZoneName: 'short'
        });
    } catch (e) {
        return date.toString();
    }
}

function _formatUtcDateTime(date) {
    // Format as UTC with timezone label
    try {
        return date.toLocaleString(undefined, {
            month: 'short', day: 'numeric', year: 'numeric',
            hour: 'numeric', minute: '2-digit',
            timeZone: 'UTC', timeZoneName: 'short'
        });
    } catch (e) {
        return date.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
    }
}

function updateRelativeTimes() {
    document.querySelectorAll('[data-timestamp]').forEach(function(el) {
        var iso = el.getAttribute('data-timestamp');
        var date = _parseUtcTimestamp(iso);
        if (!date || isNaN(date.getTime())) return;

        el.textContent = relativeTime(iso);

        // Tooltip: show local time (and UTC if different from local)
        var localStr = _formatLocalDateTime(date);
        var utcStr = _formatUtcDateTime(date);
        if (localStr !== utcStr) {
            el.setAttribute('title', localStr + '\n' + utcStr);
        } else {
            el.setAttribute('title', utcStr);
        }
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
    if (params.has('bulk_deleted')) {
        var n = params.get('bulk_deleted');
        showToast('Deleted ' + n + ' email' + (n === '1' ? '' : 's'));
    }
    if (params.has('cleanup')) {
        showToast('Cleanup completed');
    }
});
