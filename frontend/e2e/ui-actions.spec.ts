import { test, expect, type Page } from '@playwright/test';

/**
 * E2E tests for UI Actions triggered by the chatbot.
 * These tests verify that each action type works correctly across all pages.
 */

// Helper to dispatch an action via browser console
async function dispatchAction(page: Page, type: string, params: Record<string, any> = {}) {
	return await page.evaluate(
		({ type, params }) => {
			// @ts-ignore - actionStore is available on window in dev
			const store = (window as any).__actionStore;
			if (!store) {
				throw new Error('actionStore not available on window');
			}
			store.dispatch({ type, params });
			return store.executeCurrentAction();
		},
		{ type, params }
	);
}

// Helper to check registered actions
async function getRegisteredActions(page: Page): Promise<string[]> {
	return await page.evaluate(() => {
		const store = (window as any).__actionStore;
		return store ? store.getRegisteredActions() : [];
	});
}

// Helper to login (mock or real depending on test env)
async function login(page: Page) {
	// For E2E tests, you'd typically use a test account or mock auth
	// This is a placeholder - implement based on your auth setup
	await page.goto('/');
	// Add login steps here if needed
}

test.describe('Home Page Actions', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto('/');
		// Wait for page to load and handlers to register
		await page.waitForTimeout(1000);
	});

	test('should have registered handlers for home page actions', async ({ page }) => {
		const actions = await getRegisteredActions(page);
		expect(actions).toContain('select_topic_tab');
		expect(actions).toContain('select_topic');
		expect(actions).toContain('search_articles');
		expect(actions).toContain('open_article');
	});

	test('select_topic should switch topic tab and update URL', async ({ page }) => {
		const result = await dispatchAction(page, 'select_topic', { topic: 'macro' });
		expect(result?.success).toBe(true);
		await expect(page).toHaveURL(/\?tab=macro/);
	});

	test('select_topic_tab should switch to search tab', async ({ page }) => {
		const result = await dispatchAction(page, 'select_topic_tab', { topic: 'search' });
		expect(result?.success).toBe(true);
		await expect(page).toHaveURL(/\?tab=search/);
	});

	test('search_articles should perform search and switch to search tab', async ({ page }) => {
		const result = await dispatchAction(page, 'search_articles', { search_query: 'test query' });
		expect(result?.success).toBe(true);
		await expect(page).toHaveURL(/\?tab=search/);
	});

	test('clear_search should reset search results', async ({ page }) => {
		// First do a search
		await dispatchAction(page, 'search_articles', { search_query: 'test' });
		// Then clear it
		const result = await dispatchAction(page, 'clear_search');
		expect(result?.success).toBe(true);
	});
});

test.describe('Analyst Hub Actions', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto('/analyst/macro');
		await page.waitForTimeout(1000);
	});

	test('should have registered handlers for analyst hub actions', async ({ page }) => {
		const actions = await getRegisteredActions(page);
		expect(actions).toContain('create_new_article');
		expect(actions).toContain('view_article');
		expect(actions).toContain('edit_article');
		expect(actions).toContain('submit_article');
		expect(actions).toContain('select_topic');
	});

	test('select_topic should navigate to different topic', async ({ page }) => {
		const result = await dispatchAction(page, 'select_topic', { topic: 'equity' });
		expect(result?.success).toBe(true);
		await expect(page).toHaveURL(/\/analyst\/equity/);
	});
});

test.describe('Editor Hub Actions', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto('/editor/macro');
		await page.waitForTimeout(1000);
	});

	test('should have registered handlers for editor hub actions', async ({ page }) => {
		const actions = await getRegisteredActions(page);
		expect(actions).toContain('view_article');
		expect(actions).toContain('publish_article');
		expect(actions).toContain('reject_article');
		expect(actions).toContain('select_topic');
	});
});

test.describe('Topic Admin Actions', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto('/admin');
		await page.waitForTimeout(1000);
	});

	test('should have registered handlers for topic admin actions', async ({ page }) => {
		const actions = await getRegisteredActions(page);
		expect(actions).toContain('select_topic');
		expect(actions).toContain('focus_article');
		expect(actions).toContain('deactivate_article');
		expect(actions).toContain('reactivate_article');
		expect(actions).toContain('recall_article');
		expect(actions).toContain('purge_article');
	});

	test('select_topic should switch topic', async ({ page }) => {
		const result = await dispatchAction(page, 'select_topic', { topic: 'equity' });
		expect(result?.success).toBe(true);
	});
});

test.describe('Global Admin Actions', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto('/admin/global');
		await page.waitForTimeout(1000);
	});

	test('should have registered handlers for global admin actions', async ({ page }) => {
		const actions = await getRegisteredActions(page);
		expect(actions).toContain('switch_global_view');
		expect(actions).toContain('select_topic');
		expect(actions).toContain('delete_resource');
		expect(actions).toContain('select_resource');
	});

	test('switch_global_view should switch between views', async ({ page }) => {
		const result = await dispatchAction(page, 'switch_global_view', { view: 'groups' });
		expect(result?.success).toBe(true);
	});
});

test.describe('Profile Page Actions', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto('/profile');
		await page.waitForTimeout(1000);
	});

	test('should have registered handlers for profile actions', async ({ page }) => {
		const actions = await getRegisteredActions(page);
		expect(actions).toContain('switch_profile_tab');
		expect(actions).toContain('save_tonality');
	});

	test('switch_profile_tab should switch tabs', async ({ page }) => {
		const result = await dispatchAction(page, 'switch_profile_tab', { tab: 'settings' });
		expect(result?.success).toBe(true);
	});
});

test.describe('Action Error Handling', () => {
	test('should return error for missing required params', async ({ page }) => {
		await page.goto('/');
		await page.waitForTimeout(1000);

		const result = await dispatchAction(page, 'select_topic', {});
		expect(result?.success).toBe(false);
		expect(result?.error).toContain('No topic specified');
	});

	test('should return error for unregistered action on wrong page', async ({ page }) => {
		await page.goto('/');
		await page.waitForTimeout(1000);

		// Try to execute an admin action on home page
		const result = await dispatchAction(page, 'purge_article', { article_id: 1, confirmed: true });
		expect(result?.success).toBe(false);
		expect(result?.error).toContain('No handler available');
	});
});

test.describe('Confirmation Actions', () => {
	test('deactivate_article should require confirmation', async ({ page }) => {
		await page.goto('/admin');
		await page.waitForTimeout(1000);

		// Without confirmed flag
		const result1 = await dispatchAction(page, 'deactivate_article', { article_id: 1 });
		expect(result1?.success).toBe(false);
		expect(result1?.error).toContain('requires confirmation');

		// With confirmed flag (would work if article exists)
		const result2 = await dispatchAction(page, 'deactivate_article', {
			article_id: 1,
			confirmed: true
		});
		// Will fail because article doesn't exist, but not because of confirmation
		expect(result2?.error).not.toContain('requires confirmation');
	});
});

// Comprehensive action coverage test
test.describe('All Actions Coverage', () => {
	const pageActionMap = {
		'/': [
			'select_topic_tab',
			'select_topic',
			'search_articles',
			'clear_search',
			'open_article',
			'rate_article',
			'download_pdf',
			'close_modal',
			'select_article'
		],
		'/analyst/macro': [
			'create_new_article',
			'view_article',
			'edit_article',
			'submit_article',
			'select_topic',
			'download_pdf',
			'close_modal',
			'select_article'
		],
		'/editor/macro': [
			'view_article',
			'publish_article',
			'reject_article',
			'select_topic',
			'download_pdf',
			'close_modal',
			'select_article'
		],
		'/admin': [
			'select_topic',
			'focus_article',
			'deactivate_article',
			'reactivate_article',
			'recall_article',
			'purge_article'
		],
		'/admin/global': ['switch_global_view', 'select_topic', 'delete_resource', 'select_resource'],
		'/profile': ['switch_profile_tab', 'save_tonality', 'delete_account']
	};

	for (const [path, expectedActions] of Object.entries(pageActionMap)) {
		test(`${path} should have all expected action handlers`, async ({ page }) => {
			await page.goto(path);
			await page.waitForTimeout(1000);

			const registeredActions = await getRegisteredActions(page);

			for (const action of expectedActions) {
				expect(registeredActions, `Missing handler for ${action} on ${path}`).toContain(action);
			}
		});
	}
});
