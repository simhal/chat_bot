import { writable } from 'svelte/store';
import { browser } from '$app/environment';

interface AuthState {
    isAuthenticated: boolean;
    accessToken: string | null;
    refreshToken: string | null;
    user: {
        id?: string;
        name?: string;
        surname?: string;
        email?: string;
        picture?: string;
        scopes?: string[];
    } | null;
}

const initialState: AuthState = {
    isAuthenticated: false,
    accessToken: null,
    refreshToken: null,
    user: null
};

// Load from localStorage if in browser
function loadAuthState(): AuthState {
    if (browser) {
        const stored = localStorage.getItem('authState');
        if (stored) {
            try {
                return JSON.parse(stored);
            } catch (e) {
                console.error('Failed to parse auth state', e);
            }
        }
    }
    return initialState;
}

function createAuthStore() {
    const { subscribe, set, update } = writable<AuthState>(loadAuthState());

    return {
        subscribe,
        login: (accessToken: string, refreshToken: string, user: any) => {
            const newState = {
                isAuthenticated: true,
                accessToken,
                refreshToken,
                user
            };
            set(newState);
            if (browser) {
                localStorage.setItem('authState', JSON.stringify(newState));
            }
        },
        updateTokens: (accessToken: string, refreshToken: string) => {
            update(state => {
                const newState = { ...state, accessToken, refreshToken };
                if (browser) {
                    localStorage.setItem('authState', JSON.stringify(newState));
                }
                return newState;
            });
        },
        logout: async () => {
            // Get current state to extract refresh token
            const currentState = loadAuthState();

            // Call logout API to revoke tokens on the server
            if (browser && currentState.accessToken) {
                try {
                    const { logout: logoutApi } = await import('$lib/api');
                    await logoutApi(currentState.refreshToken);
                } catch (error) {
                    console.error('Failed to revoke tokens on server:', error);
                    // Continue with local logout even if API call fails
                }
            }

            // Clear local state
            set(initialState);
            if (browser) {
                localStorage.removeItem('authState');
            }
        },
        updateUser: (user: any) => {
            update(state => {
                const newState = { ...state, user };
                if (browser) {
                    localStorage.setItem('authState', JSON.stringify(newState));
                }
                return newState;
            });
        }
    };
}

export const auth = createAuthStore();
