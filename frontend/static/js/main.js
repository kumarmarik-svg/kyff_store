/* ============================================================
   MAIN.JS — KYFF Store
   Shared utilities used across all pages
   ============================================================ */


// ── Format Currency ────────────────────────────────────────
function formatPrice(amount) {
    return `₹${parseFloat(amount).toFixed(2)}`;
}


// ── Format Date ────────────────────────────────────────────
function formatDate(str, includeTime = false) {
    if (!str) return '';
    const options = { day: 'numeric', month: 'short', year: 'numeric' };
    if (includeTime) {
        options.hour   = '2-digit';
        options.minute = '2-digit';
    }
    return new Date(str).toLocaleDateString('en-IN', options);
}


// ── Capitalize ─────────────────────────────────────────────
function capitalize(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1);
}


// ── Render Stars ───────────────────────────────────────────
function renderStars(rating) {
    const full  = Math.floor(rating || 0);
    const empty = 5 - full;
    return '★'.repeat(full) + '☆'.repeat(empty);
}


// ── Debounce ───────────────────────────────────────────────
function debounce(fn, delay = 300) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}


// ── Throttle ───────────────────────────────────────────────
function throttle(fn, limit = 300) {
    let lastCall = 0;
    return function(...args) {
        const now = Date.now();
        if (now - lastCall >= limit) {
            lastCall = now;
            fn.apply(this, args);
        }
    };
}


// ── Show Toast ─────────────────────────────────────────────
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const icons = {
        success : '✅',
        error   : '❌',
        warning : '⚠️',
        info    : 'ℹ️',
    };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span>${icons[type] || '✅'}</span>
        <span>${message}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOutRight 300ms ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}


// ── Update Cart Badge ──────────────────────────────────────
function updateCartBadge(count) {
    const badge = document.getElementById('cart-count');
    if (!badge) return;

    if (count > 0) {
        badge.textContent  = count > 99 ? '99+' : count;
        badge.style.display = 'flex';
    } else {
        badge.style.display = 'none';
    }
}


// ── Open / Close Modal ─────────────────────────────────────
function openModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add('open');
    document.body.style.overflow = 'hidden';
}

function closeModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove('open');
    document.body.style.overflow = '';
}

// Close modal on backdrop click
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-backdrop')) {
        e.target.classList.remove('open');
        document.body.style.overflow = '';
    }
});

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-backdrop.open').forEach(m => {
            m.classList.remove('open');
            document.body.style.overflow = '';
        });
    }
});


// ── Truncate Text ──────────────────────────────────────────
function truncate(str, maxLength = 100) {
    if (!str) return '';
    return str.length > maxLength
        ? str.substring(0, maxLength) + '...'
        : str;
}


// ── Validate Email ─────────────────────────────────────────
function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}


// ── Validate Phone ─────────────────────────────────────────
function isValidPhone(phone) {
    return /^[6-9]\d{9}$/.test(phone.replace(/\s+/g, ''));
}


// ── Validate Pincode ───────────────────────────────────────
function isValidPincode(pincode) {
    return /^\d{6}$/.test(pincode);
}


// ── Scroll to Top ──────────────────────────────────────────
function scrollToTop() {
    window.scrollTo({ top: 0, behavior: 'smooth' });
}


// ── Get URL Param ──────────────────────────────────────────
function getParam(key) {
    return new URLSearchParams(window.location.search).get(key);
}


// ── Set URL Param ──────────────────────────────────────────
function setParam(key, value) {
    const params = new URLSearchParams(window.location.search);
    if (value) {
        params.set(key, value);
    } else {
        params.delete(key);
    }
    window.history.replaceState({}, '', `${window.location.pathname}?${params}`);
}


// ── Copy to Clipboard ──────────────────────────────────────
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showToast('Copied to clipboard!', 'info');
    } catch {
        showToast('Could not copy', 'error');
    }
}


// ── Lazy Image Loading Fallback ────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('img[loading="lazy"]').forEach(img => {
        img.onerror = () => {
            img.src = '/static/images/placeholder.png';
        };
    });
});


// ── Auto Merge Guest Cart on Login ────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    if (Auth.isLoggedIn()) {
        const guestCart = Cart.getLocalCart();
        if (guestCart.length > 0) {
            Cart.mergeGuestCart();
        }
    }
});


// ── Active Nav Link Highlight ──────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const path  = window.location.pathname;
    const links = document.querySelectorAll('.navbar-menu a, .mobile-drawer-nav a');

    links.forEach(link => {
        if (link.getAttribute('href') === path) {
            link.classList.add('active');
        }
    });
});