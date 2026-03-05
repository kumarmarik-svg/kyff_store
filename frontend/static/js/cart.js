/* ============================================================
   CART.JS — KYFF Store
   Cart operations — add, update, remove, clear, merge
   Works for both logged-in users and guests
   ============================================================ */

const Cart = (() => {

    // ── Get Cart ───────────────────────────────────────────
    async function getCart() {
        if (Auth.isLoggedIn()) {
            return await API.get('/api/cart/');
        }

        // Guest — return local cart
        return { data: { items: getLocalCart() } };
    }


    // ── Add Item ───────────────────────────────────────────
    async function addItem(variantId, quantity = 1) {
        if (!variantId) throw new Error('Invalid product');

        if (Auth.isLoggedIn()) {
            const result = await API.post('/api/cart/add', {
                variant_id : variantId,
                quantity,
            });
            refreshBadge();
            return result;
        }

        // Guest — store locally
        addToLocalCart(variantId, quantity);
        refreshBadge();
        return { data: { items: getLocalCart() } };
    }


    // ── Update Item ────────────────────────────────────────
    async function updateItem(cartItemId, quantity) {
        if (Auth.isLoggedIn()) {
            const result = await API.patch(`/api/cart/update/${cartItemId}`, { quantity });
            refreshBadge();
            return result;
        }

        updateLocalCart(cartItemId, quantity);
        refreshBadge();
        return { data: { items: getLocalCart() } };
    }


    // ── Remove Item ────────────────────────────────────────
    async function removeItem(cartItemId) {
        if (Auth.isLoggedIn()) {
            const result = await API.delete(`/api/cart/remove/${cartItemId}`);
            refreshBadge();
            return result;
        }

        removeFromLocalCart(cartItemId);
        refreshBadge();
        return { data: { items: getLocalCart() } };
    }


    // ── Clear Cart ─────────────────────────────────────────
    async function clearCart() {
        if (Auth.isLoggedIn()) {
            const result = await API.delete('/api/cart/clear');
            refreshBadge();
            return result;
        }

        localStorage.removeItem('kyff_guest_cart');
        refreshBadge();
    }


    // ── Clear Local Cart Count ─────────────────────────────
    function clearLocalCart() {
        localStorage.removeItem('kyff_guest_cart');
        updateCartBadge(0);
    }


    // ── Merge Guest Cart on Login ──────────────────────────
    async function mergeGuestCart() {
        const localCart = getLocalCart();
        if (localCart.length === 0) return;

        try {
            await API.post('/api/cart/merge', {
                items: localCart.map(item => ({
                    variant_id : item.variant_id,
                    quantity   : item.quantity,
                }))
            });
            localStorage.removeItem('kyff_guest_cart');
            refreshBadge();
        } catch (e) {
            // Silent fail — guest cart merge is non-critical
        }
    }


    // ── Refresh Cart Badge ─────────────────────────────────
    async function refreshBadge() {
        try {
            if (Auth.isLoggedIn()) {
                const res   = await API.get('/api/cart/');
                const items = res.data?.items || [];
                const count = items.reduce((sum, item) => sum + item.quantity, 0);
                updateCartBadge(count);
            } else {
                const local = getLocalCart();
                const count = local.reduce((sum, item) => sum + item.quantity, 0);
                updateCartBadge(count);
            }
        } catch {
            updateCartBadge(0);
        }
    }


    // ── Local Cart Helpers (Guest) ─────────────────────────
    function getLocalCart() {
        try {
            const raw = localStorage.getItem('kyff_guest_cart');
            return raw ? JSON.parse(raw) : [];
        } catch {
            return [];
        }
    }

    function saveLocalCart(cart) {
        localStorage.setItem('kyff_guest_cart', JSON.stringify(cart));
    }

    function addToLocalCart(variantId, quantity) {
        const cart    = getLocalCart();
        const existing = cart.find(i => i.variant_id === variantId);

        if (existing) {
            existing.quantity += quantity;
        } else {
            cart.push({
                id         : Date.now(),  // temp local id
                variant_id : variantId,
                quantity,
            });
        }
        saveLocalCart(cart);
    }

    function updateLocalCart(itemId, quantity) {
        const cart    = getLocalCart();
        const idx     = cart.findIndex(i => i.id === itemId);
        if (idx !== -1) {
            if (quantity <= 0) {
                cart.splice(idx, 1);
            } else {
                cart[idx].quantity = quantity;
            }
        }
        saveLocalCart(cart);
    }

    function removeFromLocalCart(itemId) {
        const cart = getLocalCart().filter(i => i.id !== itemId);
        saveLocalCart(cart);
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