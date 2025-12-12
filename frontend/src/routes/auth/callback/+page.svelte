<script lang="ts">
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import { page } from '$app/stores';
    import { auth } from '$lib/stores/auth';
    import { PUBLIC_LINKEDIN_CLIENT_ID, PUBLIC_LINKEDIN_REDIRECT_URI, PUBLIC_API_URL } from '$env/static/public';

    let error = '';
    let loading = true;

    // Helper function to decode base64url (JWT uses base64url, not standard base64)
    function base64urlDecode(str: string): string {
        // Convert base64url to base64
        let base64 = str.replace(/-/g, '+').replace(/_/g, '/');

        // Add padding if needed
        const pad = base64.length % 4;
        if (pad) {
            if (pad === 1) {
                throw new Error('Invalid base64url string');
            }
            base64 += new Array(5 - pad).join('=');
        }

        // Decode base64
        return atob(base64);
    }

    onMount(async () => {
        try {
            const code = $page.url.searchParams.get('code');
            const state = $page.url.searchParams.get('state');
            const errorParam = $page.url.searchParams.get('error');

            if (errorParam) {
                error = `LinkedIn authentication error: ${errorParam}`;
                loading = false;
                return;
            }

            if (!code) {
                error = 'No authorization code received';
                loading = false;
                return;
            }

            // Exchange code for tokens via our backend (keeps client_secret secure)
            const tokenResponse = await fetch(`${PUBLIC_API_URL}/api/auth/token`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    code: code,
                    redirect_uri: PUBLIC_LINKEDIN_REDIRECT_URI
                })
            });

            if (!tokenResponse.ok) {
                const errorData = await tokenResponse.json();
                error = `Failed to exchange code: ${errorData.detail || 'Unknown error'}`;
                loading = false;
                return;
            }

            const tokens = await tokenResponse.json();
            const accessToken = tokens.access_token;
            const refreshToken = tokens.refresh_token;

            if (!accessToken || !refreshToken) {
                error = 'No tokens received from server';
                loading = false;
                return;
            }

            // Decode the access token to get user info
            const payload = JSON.parse(base64urlDecode(accessToken.split('.')[1]));

            // Store authentication state
            auth.login(accessToken, refreshToken, {
                id: payload.sub,
                name: payload.name,
                surname: payload.surname,
                email: payload.email,
                picture: payload.picture,
                scopes: payload.scopes || []
            });

            // Redirect to home page
            goto('/');
        } catch (e) {
            error = `Authentication failed: ${e instanceof Error ? e.message : 'Unknown error'}`;
            loading = false;
        }
    });
</script>

<div class="container">
    {#if loading}
        <div class="loading">
            <div class="spinner"></div>
            <p>Completing authentication...</p>
        </div>
    {:else if error}
        <div class="error">
            <h2>Authentication Error</h2>
            <p>{error}</p>
            <a href="/">Return to home</a>
        </div>
    {/if}
</div>

<style>
    .container {
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 100vh;
        padding: 2rem;
    }

    .loading, .error {
        text-align: center;
        max-width: 400px;
    }

    .spinner {
        border: 4px solid #f3f3f3;
        border-top: 4px solid #0066cc;
        border-radius: 50%;
        width: 40px;
        height: 40px;
        animation: spin 1s linear infinite;
        margin: 0 auto 1rem;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    .error {
        color: #d32f2f;
    }

    .error h2 {
        margin-bottom: 1rem;
    }

    .error a {
        display: inline-block;
        margin-top: 1rem;
        color: #0066cc;
        text-decoration: none;
    }

    .error a:hover {
        text-decoration: underline;
    }
</style>
