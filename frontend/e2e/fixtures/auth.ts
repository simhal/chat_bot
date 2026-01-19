import { type Page } from '@playwright/test';

/**
 * Mock auth state for E2E testing.
 * These fixtures simulate different user roles for testing auth-protected pages.
 */

export interface MockUser {
	id: string;
	name: string;
	surname: string;
	email: string;
	picture: string;
	scopes: string[];
}

export interface MockAuthState {
	isAuthenticated: boolean;
	accessToken: string;
	refreshToken: string;
	user: MockUser;
}

// =============================================================================
// Mock Users with Different Roles
// =============================================================================

/**
 * Reader user - basic access to published articles
 */
export const readerUser: MockUser = {
	id: '1',
	name: 'Test',
	surname: 'Reader',
	email: 'reader@test.com',
	picture: '',
	scopes: ['macro:reader', 'equity:reader', 'credit:reader']
};

/**
 * Analyst user - can create and edit articles
 */
export const analystUser: MockUser = {
	id: '2',
	name: 'Test',
	surname: 'Analyst',
	email: 'analyst@test.com',
	picture: '',
	scopes: ['macro:reader', 'macro:analyst', 'equity:reader', 'equity:analyst']
};

/**
 * Editor user - can review and publish articles
 */
export const editorUser: MockUser = {
	id: '3',
	name: 'Test',
	surname: 'Editor',
	email: 'editor@test.com',
	picture: '',
	scopes: ['macro:reader', 'macro:analyst', 'macro:editor', 'equity:reader', 'equity:analyst', 'equity:editor']
};

/**
 * Topic admin user - can manage articles within topics
 */
export const topicAdminUser: MockUser = {
	id: '4',
	name: 'Test',
	surname: 'TopicAdmin',
	email: 'topicadmin@test.com',
	picture: '',
	scopes: ['macro:reader', 'macro:analyst', 'macro:editor', 'macro:admin', 'equity:reader', 'equity:analyst', 'equity:editor', 'equity:admin']
};

/**
 * Global admin user - full access to everything
 */
export const globalAdminUser: MockUser = {
	id: '5',
	name: 'Test',
	surname: 'GlobalAdmin',
	email: 'globaladmin@test.com',
	picture: '',
	scopes: ['global:admin', 'macro:reader', 'macro:analyst', 'macro:editor', 'macro:admin', 'equity:reader', 'equity:analyst', 'equity:editor', 'equity:admin']
};

// =============================================================================
// Auth State Builders
// =============================================================================

/**
 * Create a mock auth state for a given user
 */
export function createAuthState(user: MockUser): MockAuthState {
	return {
		isAuthenticated: true,
		accessToken: `mock-access-token-${user.id}`,
		refreshToken: `mock-refresh-token-${user.id}`,
		user
	};
}

// Pre-built auth states for convenience
export const readerAuthState = createAuthState(readerUser);
export const analystAuthState = createAuthState(analystUser);
export const editorAuthState = createAuthState(editorUser);
export const topicAdminAuthState = createAuthState(topicAdminUser);
export const globalAdminAuthState = createAuthState(globalAdminUser);

// =============================================================================
// Playwright Helpers
// =============================================================================

/**
 * Inject mock auth state into localStorage before navigating to a page.
 * Also intercepts API calls to prevent token refresh failures from logging out.
 */
export async function loginAs(page: Page, authState: MockAuthState): Promise<void> {
	// Intercept token refresh calls to prevent logout on 401
	await page.route('**/api/auth/refresh', async (route) => {
		// Return a successful refresh response with the same tokens
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify({
				access_token: authState.accessToken,
				refresh_token: authState.refreshToken
			})
		});
	});

	// Intercept /api/me endpoint to return mock user data
	await page.route('**/api/me', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify({
				id: parseInt(authState.user.id),
				email: authState.user.email,
				name: authState.user.name,
				surname: authState.user.surname,
				picture: authState.user.picture,
				scopes: authState.user.scopes,
				groups: []
			})
		});
	});

	// Intercept entitled topics endpoint to return mock topics for tests
	await page.route('**/api/topics/entitled**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify([
				{ id: 1, slug: 'macro', title: 'Macro', description: 'Macroeconomics', active: true, visible: true },
				{ id: 2, slug: 'equity', title: 'Equity', description: 'Equity markets', active: true, visible: true },
				{ id: 3, slug: 'credit', title: 'Credit', description: 'Credit markets', active: true, visible: true }
			])
		});
	});

	// Intercept admin users endpoint
	await page.route('**/api/admin/users**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify([
				{ id: 1, email: 'test@test.com', name: 'Test', surname: 'User', is_banned: false, groups: [] }
			])
		});
	});

	// Intercept admin groups endpoint
	await page.route('**/api/admin/groups**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify([
				{ id: 1, name: 'TestGroup', description: 'Test group', members: [] }
			])
		});
	});

	// Intercept topics endpoint
	await page.route('**/api/topics', async (route) => {
		if (route.request().method() === 'GET') {
			await route.fulfill({
				status: 200,
				contentType: 'application/json',
				body: JSON.stringify([
					{ id: 1, slug: 'macro', title: 'Macro', description: 'Macroeconomics', active: true, visible: true, display_order: 1 },
					{ id: 2, slug: 'equity', title: 'Equity', description: 'Equity markets', active: true, visible: true, display_order: 2 }
				])
			});
		} else {
			await route.continue();
		}
	});

	// Intercept admin articles endpoint
	await page.route('**/api/admin/articles**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify([
				{ id: 1, headline: 'Test Article', status: 'published', topic: 'macro', author: 'Test', created_at: new Date().toISOString() }
			])
		});
	});

	// Intercept tonalities endpoint
	await page.route('**/api/tonalities**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify([
				{ id: 1, name: 'Professional', description: 'Professional tone', is_default: true }
			])
		});
	});

	// Intercept user tonality endpoint
	await page.route('**/api/user/tonality**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify({
				chat_tonality: null,
				content_tonality: null
			})
		});
	});

	// Intercept prompts endpoint
	await page.route('**/api/prompts**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify([])
		});
	});

	// Intercept user profile endpoint
	await page.route('**/api/user/profile**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify({
				id: parseInt(authState.user.id),
				email: authState.user.email,
				name: authState.user.name,
				surname: authState.user.surname,
				picture: authState.user.picture,
				created_at: new Date().toISOString(),
				custom_prompt: null,
				groups: []
			})
		});
	});

	// Intercept user settings endpoint
	await page.route('**/api/user/settings**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify({
				chat_tonality: null,
				content_tonality: null,
				notifications: true
			})
		});
	});

	// Intercept global resources endpoint
	await page.route('**/api/resources/global**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify({ resources: [] })
		});
	});

	// Intercept articles endpoints for reader/analyst/editor
	await page.route('**/api/articles**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify([])
		});
	});

	// Intercept analyst articles endpoint (drafts list)
	await page.route('**/api/analyst/*/articles**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify([
				{
					id: 1,
					headline: 'Draft Article',
					status: 'draft',
					topic: 'macro',
					author_name: authState.user.name,
					created_at: new Date().toISOString(),
					updated_at: new Date().toISOString()
				}
			])
		});
	});

	// Intercept editor articles endpoint (review queue)
	await page.route('**/api/editor/*/articles**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify([
				{
					id: 1,
					headline: 'Article for Review',
					status: 'submitted',
					topic: 'macro',
					author_name: 'Test Author',
					created_at: new Date().toISOString(),
					updated_at: new Date().toISOString()
				}
			])
		});
	});

	// Intercept reader published articles endpoint
	await page.route('**/api/reader/*/published**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify([
				{
					id: 1,
					headline: 'Published Article',
					summary: 'This is a published article summary.',
					topic: 'macro',
					author_name: 'Test Author',
					published_at: new Date().toISOString()
				}
			])
		});
	});

	// Intercept reader search endpoint
	await page.route('**/api/reader/*/search**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify([])
		});
	});

	// Intercept analyst article detail endpoint
	await page.route('**/api/analyst/*/article/*', async (route) => {
		// Skip if this is the articles list endpoint
		if (route.request().url().includes('/articles')) {
			await route.continue();
			return;
		}
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify({
				id: 123,
				headline: 'Original Headline',
				content: 'Original content.',
				keywords: 'original, keywords',
				status: 'draft',
				topic: 'macro',
				author_name: authState.user.name,
				created_at: new Date().toISOString(),
				updated_at: new Date().toISOString()
			})
		});
	});

	// Intercept reader article detail endpoint
	await page.route('**/api/reader/*/article/*', async (route) => {
		// Skip if this is resources or other sub-endpoints
		if (route.request().url().includes('/resources') || route.request().url().includes('/rate') || route.request().url().includes('/pdf')) {
			await route.continue();
			return;
		}
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify({
				id: 1,
				headline: 'Published Article',
				content: '# Article Content\n\nThis is the article body.',
				keywords: 'test, article',
				topic: 'macro',
				author_name: 'Test Author',
				published_at: new Date().toISOString()
			})
		});
	});

	// Intercept article resources endpoint
	await page.route('**/api/reader/*/article/*/resources**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify([])
		});
	});

	// Intercept conversation history endpoint
	await page.route('**/api/chat/history**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify({ messages: [] })
		});
	});

	// Intercept admin resources endpoint (topic-specific)
	await page.route('**/api/admin/*/resources**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify({ resources: [] })
		});
	});

	// Navigate to a blank page first to set localStorage on the correct origin
	await page.goto('/');

	// Inject auth state into localStorage
	await page.evaluate((state) => {
		localStorage.setItem('authState', JSON.stringify(state));
	}, authState);

	// Reload to pick up the new auth state
	await page.reload();

	// Wait for auth state to be fully loaded by checking for auth-dependent elements
	// The app shows different UI based on auth state, so we wait for that
	await page.waitForFunction(() => {
		const stored = localStorage.getItem('authState');
		if (!stored) return false;
		try {
			const state = JSON.parse(stored);
			return state.isAuthenticated === true;
		} catch {
			return false;
		}
	}, { timeout: 5000 });

	// Wait for the app to process the auth state and enable interactive elements
	// This ensures chat input and other auth-dependent features are ready
	await page.waitForTimeout(1000);
}

/**
 * Login as a reader user
 */
export async function loginAsReader(page: Page): Promise<void> {
	await loginAs(page, readerAuthState);
}

/**
 * Login as an analyst user
 */
export async function loginAsAnalyst(page: Page): Promise<void> {
	await loginAs(page, analystAuthState);
}

/**
 * Login as an editor user
 */
export async function loginAsEditor(page: Page): Promise<void> {
	await loginAs(page, editorAuthState);
}

/**
 * Login as a topic admin user
 */
export async function loginAsTopicAdmin(page: Page): Promise<void> {
	await loginAs(page, topicAdminAuthState);
}

/**
 * Login as a global admin user
 */
export async function loginAsGlobalAdmin(page: Page): Promise<void> {
	await loginAs(page, globalAdminAuthState);
}

/**
 * Logout by clearing localStorage
 */
export async function logout(page: Page): Promise<void> {
	await page.evaluate(() => {
		localStorage.removeItem('authState');
	});
	await page.reload();
}

/**
 * Check if the page has a logged-in user
 */
export async function isLoggedIn(page: Page): Promise<boolean> {
	return await page.evaluate(() => {
		const stored = localStorage.getItem('authState');
		if (!stored) return false;
		try {
			const state = JSON.parse(stored);
			return state.isAuthenticated === true;
		} catch {
			return false;
		}
	});
}
