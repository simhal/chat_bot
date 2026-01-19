import { type Page } from '@playwright/test';

/**
 * E2E test authentication fixtures.
 *
 * These functions authenticate test users via the dev-login endpoint
 * (only available when TESTING=true in the backend).
 *
 * Test users (from seed_test_data.py):
 * - reader@test.com (reader access)
 * - analyst@test.com (macro:analyst)
 * - editor@test.com (macro:editor)
 * - topicadmin@test.com (macro:admin)
 * - admin@test.com (global:admin)
 */

const API_URL = process.env.API_URL || 'http://localhost:8004';

interface AuthResponse {
	access_token: string;
	refresh_token: string;
	token_type: string;
	user: {
		id: string;
		email: string;
		name: string;
		surname: string;
		picture: string | null;
		scopes: string[];
	};
}

/**
 * Login as a test user via the dev-login endpoint.
 * Sets auth state in localStorage for the page.
 */
async function loginAs(page: Page, email: string): Promise<void> {
	// Call dev-login endpoint
	const response = await fetch(`${API_URL}/api/auth/dev-login`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ email })
	});

	if (!response.ok) {
		const error = await response.text();
		throw new Error(`Failed to login as ${email}: ${error}`);
	}

	const auth: AuthResponse = await response.json();

	// Set auth state in localStorage via page context
	await page.addInitScript(
		(authState) => {
			localStorage.setItem('authState', JSON.stringify(authState));
		},
		{
			isAuthenticated: true,
			accessToken: auth.access_token,
			refreshToken: auth.refresh_token,
			user: auth.user
		}
	);
}

/**
 * Login as a reader (basic access).
 */
export async function loginAsReader(page: Page): Promise<void> {
	await loginAs(page, 'reader@test.com');
}

/**
 * Login as an analyst (can create/edit articles).
 */
export async function loginAsAnalyst(page: Page): Promise<void> {
	await loginAs(page, 'analyst@test.com');
}

/**
 * Login as an editor (can review/publish articles).
 */
export async function loginAsEditor(page: Page): Promise<void> {
	await loginAs(page, 'editor@test.com');
}

/**
 * Login as a topic admin (can manage topic settings).
 */
export async function loginAsTopicAdmin(page: Page): Promise<void> {
	await loginAs(page, 'topicadmin@test.com');
}

/**
 * Login as a global admin (full system access).
 */
export async function loginAsGlobalAdmin(page: Page): Promise<void> {
	await loginAs(page, 'admin@test.com');
}

/**
 * Logout - clear auth state from localStorage.
 */
export async function logout(page: Page): Promise<void> {
	await page.addInitScript(() => {
		localStorage.removeItem('authState');
	});
}
