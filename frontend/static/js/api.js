/* ============================================================
   API.JS — KYFF Store
   Central API client — all fetch() calls go through here
   ============================================================ */

const API = (() => {

    const BASE_URL = '';  // Same origin — Flask serves both

    // ── Core Request ───────────────────────────────────────
    async function request(method, endpoint, body = null, isFormData = false) {
        const headers = {};

        // Auth token
        const token = localStorage.getItem('kyff_access_token');
        if (token) headers['Authorization'] = `Bearer ${token}`;

        // Guest cart session token — only sent when not logged in
        const sessionToken = sessionStorage.getItem('kyff_session_token');
        if (sessionToken && !token) headers['X-Session-Token'] = sessionToken;

        // Content type — skip for FormData
        if (!isFormData && body) {
            headers['Content-Type'] = 'application/json';
        }

        const config = {
            method,
            headers,
        };

        if (body) {
            config.body = isFormData ? body : JSON.stringify(body);
        }

        let response;
        try {
            response = await fetch(`${BASE_URL}${endpoint}`, config);
        } catch (networkErr) {
            throw new Error('Network error — please check your connection');
        }

        // Handle 401 — token expired
        // Skip refresh logic for login/register: a 401 there means wrong credentials,
        // not an expired token. Let it fall through to the normal error handler below.
        const skipRefresh = endpoint === '/api/auth/login' || endpoint === '/api/auth/register';
        if (response.status === 401 && !skipRefresh) {
            const refreshed = await tryRefreshToken();
            if (refreshed) {
                // Retry original request with new token
                const newToken = localStorage.getItem('kyff_access_token');
                headers['Authorization'] = `Bearer ${newToken}`;
                response = await fetch(`${BASE_URL}${endpoint}`, config);
            } else {
                // Clear auth and redirect to login
                Auth.clearSession();
                window.location.href = `/auth/login?next=${window.location.pathname}`;
                return;
            }
        }

        // Parse JSON
        let data;
        try {
            data = await response.json();
        } catch {
            throw new Error('Invalid response from server');
        }

        // Handle errors
        if (!response.ok) {
            const message = data?.message || data?.error || `Error ${response.status}`;
            throw new Error(message);
        }

        return data;
    }


    // ── Token Refresh ──────────────────────────────────────
    async function tryRefreshToken() {
        const refreshToken = localStorage.getItem('kyff_refresh_token');
        if (!refreshToken) return false;

        try {
            const response = await fetch(`${BASE_URL}/api/auth/refresh`, {
                method  : 'POST',
                headers : {
                    'Authorization' : `Bearer ${refreshToken}`,
                    'Content-Type'  : 'application/json',
                },
            });

            if (!response.ok) return false;

            const data = await response.json();
            if (data?.data?.access_token) {
                localStorage.setItem('kyff_access_token', data.data.access_token);
                return true;
            }
            return false;
        } catch {
            return false;
        }
    }


    // ── Public Methods ─────────────────────────────────────
    return {
        get    : (endpoint)              => request('GET',    endpoint),
        post   : (endpoint, body)        => request('POST',   endpoint, body),
        patch  : (endpoint, body)        => request('PATCH',  endpoint, body),
        put    : (endpoint, body)        => request('PUT',    endpoint, body),
        delete : (endpoint)              => request('DELETE', endpoint),
        upload : (endpoint, formData)    => request('POST',   endpoint, formData, true),
    };

})();