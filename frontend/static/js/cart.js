/* ============================================================
   CART.JS — KYFF Store
   Cart operations — add, update, remove, clear, merge
   Works for both logged-in users and guests.
   Guest carts use the backend via X-Session-Token (set by api.js).
   Session token is stored in localStorage as 'kyff_session_token'.
   ============================================================ */

const Cart = (() => {

    const SESSION_KEY = 'kyff_session_token';


    // ── Save session token from backend response ────────────
    // Backend returns session_token only when a new guest cart is created.
    function _saveSessionToken(data) {
        if (data?.session_token) {
            sessionStorage.setItem(SESSION_KEY, data.session_token);
        }
    }


    // ── Update badge from cart data ────────────────────────
    function _badgeFromData(data) {
        const count = (data?.items || []).reduce((sum, i) => sum + i.quantity, 0);
        updateCartBadge(count);
    }


    // ── Get Cart ───────────────────────────────────────────
    async function getCart() {
        // Don't hit the backend if there's nothing to load —
        // avoids creating empty guest cart rows on every page load.
        if (!Auth.isLoggedIn() && !sessionStorage.getItem(SESSION_KEY)) {
            return { data: { items: [], total_items: 0, subtotal: 0 } };
        }

        const res = await API.get('/api/cart/');
        _saveSessionToken(res.data);
        return res;
    }


    // ── Add Item ───────────────────────────────────────────
    async function addItem(variantId, quantity = 1) {
        if (!variantId) throw new Error('Invalid product');

        const result = await API.post('/api/cart/add', { variant_id: variantId, quantity });
        _saveSessionToken(result.data);
        _badgeFromData(result.data);
        return result;
    }


    // ── Update Item ────────────────────────────────────────
    async function updateItem(cartItemId, quantity) {
        const result = await API.patch(`/api/cart/update/${cartItemId}`, { quantity });
        _badgeFromData(result.data);
        return result;
    }


    // ── Remove Item ────────────────────────────────────────
    async function removeItem(cartItemId) {
        const result = await API.delete(`/api/cart/remove/${cartItemId}`);
        _badgeFromData(result.data);
        return result;
    }


    // ── Clear Cart ─────────────────────────────────────────
    async function clearCart() {
        const result = await API.delete('/api/cart/clear');
        _badgeFromData(result.data);
        return result;
    }


    // ── Clear Local Cart (called after logout) ─────────────
    function clearLocalCart() {
        sessionStorage.removeItem(SESSION_KEY);
        localStorage.removeItem('kyff_guest_cart'); // remove legacy key
        updateCartBadge(0);
    }


    // ── Merge Guest Cart on Login ──────────────────────────
    // Sends session_token (the backend cart identifier) to the merge endpoint.
    // Backend merges guest items into the user's DB cart and deletes the guest cart.
    async function mergeGuestCart() {
        const sessionToken = sessionStorage.getItem(SESSION_KEY);
        if (!sessionToken) return;

        try {
            await API.post('/api/cart/merge', { session_token: sessionToken });
            sessionStorage.removeItem(SESSION_KEY);
            await refreshBadge();
        } catch (e) {
            // Silent fail — merge is non-critical
        }
    }


    // ── Refresh Cart Badge ─────────────────────────────────
    async function refreshBadge() {
        try {
            if (!Auth.isLoggedIn() && !sessionStorage.getItem(SESSION_KEY)) {
                updateCartBadge(0);
                return;
            }
            const res = await API.get('/api/cart/');
            _saveSessionToken(res.data);
            _badgeFromData(res.data);
        } catch {
            updateCartBadge(0);
        }
    }


    // ── getLocalCart — kept for backward compat ────────────
    function getLocalCart() {
        return [];
    }


    // ── Public ─────────────────────────────────────────────
    return {
        getCart,
        addItem,
        updateItem,
        removeItem,
        clearCart,
        clearLocalCart,
        mergeGuestCart,
        refreshBadge,
        getLocalCart,
    };

})();