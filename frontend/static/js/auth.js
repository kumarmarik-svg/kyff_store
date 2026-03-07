/* ============================================================
   AUTH.JS — KYFF Store
   Login, register, logout, token management, session helpers
   ============================================================ */

const Auth = (() => {

    const KEYS = {
        access_token  : 'kyff_access_token',
        refresh_token : 'kyff_refresh_token',
        user          : 'kyff_user',
    };


    // ── Login ──────────────────────────────────────────────
    async function login(email, password) {
        const data = await API.post('/api/auth/login', { email, password });

        const { access_token, refresh_token, user } = data.data;

        localStorage.setItem(KEYS.access_token,  access_token);
        localStorage.setItem(KEYS.refresh_token, refresh_token);
        localStorage.setItem(KEYS.user,          JSON.stringify(user));

        // Merge any existing guest cart into the user's DB cart.
        // Must run after tokens are saved so the API call is authenticated.
        await Cart.mergeGuestCart();

        return user;
    }


    // ── Register ───────────────────────────────────────────
    async function register({ name, email, phone, password }) {
        const data = await API.post('/api/auth/register', {
            name, email, phone, password
        });

        const { access_token, refresh_token, user } = data.data;

        localStorage.setItem(KEYS.access_token,  access_token);
        localStorage.setItem(KEYS.refresh_token, refresh_token);
        localStorage.setItem(KEYS.user,          JSON.stringify(user));

        // Merge any existing guest cart into the new user's DB cart.
        await Cart.mergeGuestCart();

        return user;
    }


    // ── Logout ─────────────────────────────────────────────
    function logout() {
        clearSession();
        window.location.href = '/auth/login';
    }


    // ── Clear Session ──────────────────────────────────────
    function clearSession() {
        localStorage.removeItem(KEYS.access_token);
        localStorage.removeItem(KEYS.refresh_token);
        localStorage.removeItem(KEYS.user);
        localStorage.removeItem('kyff_cart_id');
        // Clear guest cart session so the old guest cart never reappears after logout.
        sessionStorage.removeItem('kyff_session_token');
        localStorage.removeItem('kyff_guest_cart'); // remove legacy key
    }


    // ── Get Stored User ────────────────────────────────────
    function getUser() {
        try {
            const raw = localStorage.getItem(KEYS.user);
            return raw ? JSON.parse(raw) : null;
        } catch {
            return null;
        }
    }


    // ── Is Logged In ───────────────────────────────────────
    function isLoggedIn() {
        return !!localStorage.getItem(KEYS.access_token);
    }


    // ── Is Admin ───────────────────────────────────────────
    function isAdmin() {
        const user = getUser();
        return user?.role === 'admin';
    }


    // ── Get Access Token ───────────────────────────────────
    function getToken() {
        return localStorage.getItem(KEYS.access_token);
    }


    // ── Refresh User Profile ───────────────────────────────
    async function refreshUser() {
        try {
            const data = await API.get('/api/auth/me');
            const user = data.data?.user;
            if (user) {
                localStorage.setItem(KEYS.user, JSON.stringify(user));
                await Cart.mergeGuestCart();
            }
            return user;
        } catch {
            return getUser();
        }
    }


    // ── Public ─────────────────────────────────────────────
    return {
        login,
        register,
        logout,
        clearSession,
        getUser,
        isLoggedIn,
        isAdmin,
        getToken,
        refreshUser,
    };

})();