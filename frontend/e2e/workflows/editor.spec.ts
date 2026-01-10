import { test, expect, type Page } from '@playwright/test';

/**
 * Editor Workflow E2E Tests
 *
 * Tests based on docs/12-testing-workflows.md Section 4: Editor Workflows
 * Required Role: {topic}:editor or global:admin
 */

// Helper to mock editor authentication
async function mockEditorAuth(page: Page) {
	await page.addInitScript(() => {
		const mockToken = {
			access_token: 'test-editor-token',
			user: {
				id: 3,
				email: 'editor@test.com',
				name: 'Test',
				surname: 'Editor',
				scopes: ['macro:editor', 'equity:reader']
			}
		};
		localStorage.setItem('auth', JSON.stringify(mockToken));
	});
}

test.describe('4.1 Access Editor Dashboard', () => {
	test.beforeEach(async ({ page }) => {
		await mockEditorAuth(page);
	});

	test('should load editor dashboard', async ({ page }) => {
		await page.goto('/editor/macro');

		await expect(page.locator('[data-testid="editor-dashboard"]')).toBeVisible();
	});

	test('should display articles awaiting review', async ({ page }) => {
		await page.goto('/editor/macro');

		await expect(page.locator('[data-testid="review-queue"]')).toBeVisible();
	});

	test('should show topic filter', async ({ page }) => {
		await page.goto('/editor/macro');

		// Verify we're viewing macro topic
		await expect(page.locator('h1')).toContainText(/macro/i);
	});
});

test.describe('4.2 Review Article', () => {
	test.beforeEach(async ({ page }) => {
		await mockEditorAuth(page);
	});

	test('should open article for review', async ({ page }) => {
		await page.goto('/editor/macro');

		const article = page.locator('[data-testid="review-article-item"]').first();
		if (await article.isVisible()) {
			await article.click();
			await expect(page.locator('[data-testid="article-review-view"]')).toBeVisible();
		}
	});

	test('should display full article content', async ({ page }) => {
		await page.goto('/editor/macro');

		const article = page.locator('[data-testid="review-article-item"]').first();
		if (await article.isVisible()) {
			await article.click();
			await expect(page.locator('[data-testid="article-content"]')).toBeVisible();
		}
	});

	test('should show review actions', async ({ page }) => {
		await page.goto('/editor/macro');

		const article = page.locator('[data-testid="review-article-item"]').first();
		if (await article.isVisible()) {
			await article.click();

			// Should have reject and publish buttons
			await expect(page.locator('[data-testid="reject-btn"]')).toBeVisible();
			await expect(page.locator('[data-testid="publish-btn"]')).toBeVisible();
		}
	});

	test('should have PDF preview option', async ({ page }) => {
		await page.goto('/editor/macro');

		const article = page.locator('[data-testid="review-article-item"]').first();
		if (await article.isVisible()) {
			await article.click();
			await expect(page.locator('[data-testid="download-pdf"]')).toBeVisible();
		}
	});
});

test.describe('4.3 Request Changes (Reject)', () => {
	test.beforeEach(async ({ page }) => {
		await mockEditorAuth(page);
	});

	test('should open feedback dialog on reject', async ({ page }) => {
		await page.goto('/editor/macro');

		const article = page.locator('[data-testid="review-article-item"]').first();
		if (await article.isVisible()) {
			await article.click();
			await page.click('[data-testid="reject-btn"]');

			await expect(page.locator('[data-testid="feedback-dialog"]')).toBeVisible();
		}
	});

	test('should require feedback notes', async ({ page }) => {
		await page.goto('/editor/macro');

		const article = page.locator('[data-testid="review-article-item"]').first();
		if (await article.isVisible()) {
			await article.click();
			await page.click('[data-testid="reject-btn"]');

			// Should have notes input
			await expect(page.locator('[data-testid="feedback-notes"]')).toBeVisible();
		}
	});

	test('should submit rejection with feedback', async ({ page }) => {
		await page.goto('/editor/macro');

		const article = page.locator('[data-testid="review-article-item"]').first();
		if (await article.isVisible()) {
			await article.click();
			await page.click('[data-testid="reject-btn"]');

			// Enter feedback
			await page.fill('[data-testid="feedback-notes"]', 'Please add more data sources.');
			await page.click('[data-testid="submit-rejection"]');

			// Verify success
			await expect(page.locator('[data-testid="rejection-success"]')).toBeVisible();
		}
	});
});

test.describe('4.4 Publish Article (HITL Workflow)', () => {
	test.beforeEach(async ({ page }) => {
		await mockEditorAuth(page);
	});

	test('should show confirmation on publish', async ({ page }) => {
		await page.goto('/editor/macro');

		const article = page.locator('[data-testid="review-article-item"]').first();
		if (await article.isVisible()) {
			await article.click();
			await page.click('[data-testid="publish-btn"]');

			await expect(page.locator('[data-testid="publish-confirm"]')).toBeVisible();
		}
	});

	test('should initiate HITL approval process', async ({ page }) => {
		await page.goto('/editor/macro');

		const article = page.locator('[data-testid="review-article-item"]').first();
		if (await article.isVisible()) {
			await article.click();
			await page.click('[data-testid="publish-btn"]');

			// Confirm publish
			await page.click('[data-testid="confirm-publish"]');

			// Should show pending approval status
			await expect(page.locator('[data-testid="pending-approval"]')).toBeVisible();
		}
	});
});

test.describe('4.5 Reject During HITL Approval', () => {
	test.beforeEach(async ({ page }) => {
		await mockEditorAuth(page);
	});

	test('should display approval request UI', async ({ page }) => {
		// Navigate to an article in pending_approval status
		await page.goto('/editor/macro');

		const pendingArticle = page.locator('[data-testid="pending-approval-item"]').first();
		if (await pendingArticle.isVisible()) {
			await pendingArticle.click();

			// Should have approve/reject options
			await expect(page.locator('[data-testid="approval-actions"]')).toBeVisible();
		}
	});

	test('should handle approval rejection', async ({ page }) => {
		await page.goto('/editor/macro');

		const pendingArticle = page.locator('[data-testid="pending-approval-item"]').first();
		if (await pendingArticle.isVisible()) {
			await pendingArticle.click();

			if (await page.locator('[data-testid="reject-approval"]').isVisible()) {
				await page.click('[data-testid="reject-approval"]');
				await page.fill('[data-testid="rejection-reason"]', 'Additional review needed.');
				await page.click('[data-testid="confirm-reject"]');

				// Article should return to editor queue
				await expect(page.locator('[data-testid="rejection-complete"]')).toBeVisible();
			}
		}
	});
});

test.describe('Editor Navigation', () => {
	test.beforeEach(async ({ page }) => {
		await mockEditorAuth(page);
	});

	test('should switch between topics', async ({ page }) => {
		await page.goto('/editor/macro');

		// Find topic selector
		const topicSelector = page.locator('[data-testid="topic-selector"]');
		if (await topicSelector.isVisible()) {
			await topicSelector.selectOption('equity');
			await expect(page).toHaveURL(/\/editor\/equity/);
		}
	});

	test('should return to queue after review', async ({ page }) => {
		await page.goto('/editor/macro');

		const article = page.locator('[data-testid="review-article-item"]').first();
		if (await article.isVisible()) {
			await article.click();

			// Click back button
			await page.click('[data-testid="back-to-queue"]');

			// Should be back at queue
			await expect(page.locator('[data-testid="review-queue"]')).toBeVisible();
		}
	});
});
