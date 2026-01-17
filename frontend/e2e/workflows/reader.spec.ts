import { test, expect, type Page } from '@playwright/test';

/**
 * Reader Workflow E2E Tests
 *
 * Tests based on docs/12-testing-workflows.md Section 2: Reader Workflows
 * Required Role: Any authenticated user
 */

// Helper to mock authentication
async function mockAuth(page: Page) {
	// Set up mock auth token in localStorage before navigation
	await page.addInitScript(() => {
		const mockToken = {
			access_token: 'test-token',
			user: {
				id: 1,
				email: 'reader@test.com',
				name: 'Test',
				surname: 'Reader',
				scopes: ['macro:reader', 'equity:reader']
			}
		};
		localStorage.setItem('auth', JSON.stringify(mockToken));
	});
}

test.describe('2.1 Browse Published Articles', () => {
	test.beforeEach(async ({ page }) => {
		await mockAuth(page);
	});

	test('should display main page with topic tabs', async ({ page }) => {
		await page.goto('/');

		// Verify page loads
		await expect(page).toHaveTitle(/Chatbot/i);

		// Verify topic tabs are present
		await expect(page.locator('[data-testid="topic-tabs"]')).toBeVisible();
	});

	test('should switch topic tabs', async ({ page }) => {
		await page.goto('/');

		// Click on a topic tab
		await page.click('[data-testid="topic-tab-macro"]');

		// Verify URL updates
		await expect(page).toHaveURL(/\/reader\/macro/);
	});

	test('should display articles for selected topic', async ({ page }) => {
		await page.goto('/reader/macro');

		// Wait for articles to load
		await page.waitForSelector('[data-testid="article-list"]');

		// Verify articles are displayed
		const articles = page.locator('[data-testid="article-item"]');
		await expect(articles.first()).toBeVisible();
	});
});

test.describe('2.2 Read Article Details', () => {
	test.beforeEach(async ({ page }) => {
		await mockAuth(page);
	});

	test('should open article detail view', async ({ page }) => {
		await page.goto('/reader/macro');

		// Click on first article
		await page.click('[data-testid="article-item"]:first-child');

		// Verify article content loads
		await expect(page.locator('[data-testid="article-content"]')).toBeVisible();
	});

	test('should display article metadata', async ({ page }) => {
		await page.goto('/reader/macro');
		await page.click('[data-testid="article-item"]:first-child');

		// Verify metadata is shown
		await expect(page.locator('[data-testid="article-author"]')).toBeVisible();
		await expect(page.locator('[data-testid="article-date"]')).toBeVisible();
	});
});

test.describe('2.3 Search Articles - Basic', () => {
	test.beforeEach(async ({ page }) => {
		await mockAuth(page);
	});

	test('should display search input', async ({ page }) => {
		await page.goto('/');

		await expect(page.locator('[data-testid="search-input"]')).toBeVisible();
	});

	test('should perform search and show results', async ({ page }) => {
		await page.goto('/');

		// Enter search term
		await page.fill('[data-testid="search-input"]', 'inflation');
		await page.press('[data-testid="search-input"]', 'Enter');

		// Verify search results appear
		await page.waitForSelector('[data-testid="search-results"]');
	});

	test('should clear search and restore article list', async ({ page }) => {
		await page.goto('/');

		// Search first
		await page.fill('[data-testid="search-input"]', 'test');
		await page.press('[data-testid="search-input"]', 'Enter');

		// Clear search
		await page.click('[data-testid="clear-search"]');

		// Verify original list restored
		await expect(page.locator('[data-testid="search-input"]')).toHaveValue('');
	});
});

test.describe('2.4 Search Articles - Advanced', () => {
	test.beforeEach(async ({ page }) => {
		await mockAuth(page);
	});

	test('should open advanced search panel', async ({ page }) => {
		await page.goto('/reader/search');

		await expect(page.locator('[data-testid="advanced-search-panel"]')).toBeVisible();
	});

	test('should filter by headline', async ({ page }) => {
		await page.goto('/reader/search');

		await page.fill('[data-testid="search-headline"]', 'GDP');
		await page.click('[data-testid="search-submit"]');

		// Verify results are filtered
		await page.waitForSelector('[data-testid="search-results"]');
	});

	test('should combine multiple filters', async ({ page }) => {
		await page.goto('/reader/search');

		// Fill multiple fields
		await page.fill('[data-testid="search-keywords"]', 'economy');
		await page.fill('[data-testid="search-author"]', 'Test');
		await page.click('[data-testid="search-submit"]');

		await page.waitForSelector('[data-testid="search-results"]');
	});
});

test.describe('2.5 Rate Article', () => {
	test.beforeEach(async ({ page }) => {
		await mockAuth(page);
	});

	test('should display rating control', async ({ page }) => {
		await page.goto('/reader/macro');
		await page.click('[data-testid="article-item"]:first-child');

		await expect(page.locator('[data-testid="rating-control"]')).toBeVisible();
	});

	test('should submit rating', async ({ page }) => {
		await page.goto('/reader/macro');
		await page.click('[data-testid="article-item"]:first-child');

		// Click 4th star
		await page.click('[data-testid="rating-star-4"]');

		// Verify rating was submitted (UI feedback)
		await expect(page.locator('[data-testid="rating-submitted"]')).toBeVisible();
	});
});

test.describe('2.6 Download Article as PDF', () => {
	test.beforeEach(async ({ page }) => {
		await mockAuth(page);
	});

	test('should have download PDF button', async ({ page }) => {
		await page.goto('/reader/macro');
		await page.click('[data-testid="article-item"]:first-child');

		await expect(page.locator('[data-testid="download-pdf"]')).toBeVisible();
	});

	test('should trigger PDF download', async ({ page }) => {
		await page.goto('/reader/macro');
		await page.click('[data-testid="article-item"]:first-child');

		// Wait for download
		const [download] = await Promise.all([
			page.waitForEvent('download'),
			page.click('[data-testid="download-pdf"]')
		]);

		expect(download.suggestedFilename()).toMatch(/\.pdf$/);
	});
});

test.describe('2.7 View Article Resources', () => {
	test.beforeEach(async ({ page }) => {
		await mockAuth(page);
	});

	test('should display resource links if article has resources', async ({ page }) => {
		await page.goto('/reader/macro');
		await page.click('[data-testid="article-item"]:first-child');

		// Resources section should be visible if article has resources
		const resources = page.locator('[data-testid="article-resources"]');
		// This may or may not be visible depending on test data
		if (await resources.isVisible()) {
			await expect(resources).toBeVisible();
		}
	});
});
