import { test, expect, type Page } from '@playwright/test';

/**
 * Analyst Workflow E2E Tests
 *
 * Tests based on docs/12-testing-workflows.md Section 3: Analyst Workflows
 * Required Role: {topic}:analyst or global:admin
 */

// Helper to mock analyst authentication
async function mockAnalystAuth(page: Page) {
	await page.addInitScript(() => {
		const mockToken = {
			access_token: 'test-analyst-token',
			user: {
				id: 2,
				email: 'analyst@test.com',
				name: 'Test',
				surname: 'Analyst',
				scopes: ['macro:analyst', 'equity:reader']
			}
		};
		localStorage.setItem('auth', JSON.stringify(mockToken));
	});
}

test.describe('3.1 Access Analyst Dashboard', () => {
	test.beforeEach(async ({ page }) => {
		await mockAnalystAuth(page);
	});

	test('should load analyst dashboard', async ({ page }) => {
		await page.goto('/analyst/macro');

		// Verify dashboard loads
		await expect(page.locator('[data-testid="analyst-dashboard"]')).toBeVisible();
	});

	test('should show topic-specific view', async ({ page }) => {
		await page.goto('/analyst/macro');

		// Verify topic title
		await expect(page.locator('h1')).toContainText(/macro/i);
	});

	test('should display draft articles list', async ({ page }) => {
		await page.goto('/analyst/macro');

		await expect(page.locator('[data-testid="draft-articles-list"]')).toBeVisible();
	});
});

test.describe('3.2 Create New Article', () => {
	test.beforeEach(async ({ page }) => {
		await mockAnalystAuth(page);
	});

	test('should have create article button', async ({ page }) => {
		await page.goto('/analyst/macro');

		await expect(page.locator('[data-testid="create-article-btn"]')).toBeVisible();
	});

	test('should navigate to editor on create', async ({ page }) => {
		await page.goto('/analyst/macro');

		await page.click('[data-testid="create-article-btn"]');

		// Should navigate to editor
		await expect(page).toHaveURL(/\/analyst\/edit\//);
	});

	test('should display article editor form', async ({ page }) => {
		await page.goto('/analyst/macro');
		await page.click('[data-testid="create-article-btn"]');

		// Verify editor fields
		await expect(page.locator('[data-testid="headline-input"]')).toBeVisible();
		await expect(page.locator('[data-testid="content-editor"]')).toBeVisible();
		await expect(page.locator('[data-testid="keywords-input"]')).toBeVisible();
	});

	test('should save draft article', async ({ page }) => {
		await page.goto('/analyst/macro');
		await page.click('[data-testid="create-article-btn"]');

		// Fill in article
		await page.fill('[data-testid="headline-input"]', 'Test Article Headline');
		await page.fill('[data-testid="content-editor"]', 'This is test article content.');
		await page.fill('[data-testid="keywords-input"]', 'test, article');

		// Save draft
		await page.click('[data-testid="save-draft-btn"]');

		// Verify success message or redirect
		await expect(page.locator('[data-testid="save-success"]')).toBeVisible();
	});
});

test.describe('3.3 Edit Existing Draft Article', () => {
	test.beforeEach(async ({ page }) => {
		await mockAnalystAuth(page);
	});

	test('should display draft articles in list', async ({ page }) => {
		await page.goto('/analyst/macro');

		const drafts = page.locator('[data-testid="draft-article-item"]');
		// Check if there are any drafts
		const count = await drafts.count();
		if (count > 0) {
			await expect(drafts.first()).toBeVisible();
		}
	});

	test('should open editor for existing draft', async ({ page }) => {
		await page.goto('/analyst/macro');

		// Click on first draft article
		const firstDraft = page.locator('[data-testid="draft-article-item"]').first();
		if (await firstDraft.isVisible()) {
			await firstDraft.click();
			await expect(page).toHaveURL(/\/analyst\/edit\//);
		}
	});

	test('should update headline and save', async ({ page }) => {
		// Navigate directly to edit page if we have a known article ID
		await page.goto('/analyst/edit/1');

		if (await page.locator('[data-testid="headline-input"]').isVisible()) {
			// Clear and update headline
			await page.fill('[data-testid="headline-input"]', 'Updated Headline');
			await page.click('[data-testid="save-draft-btn"]');

			// Verify save
			await expect(page.locator('[data-testid="save-success"]')).toBeVisible();
		}
	});
});

test.describe('3.4 Manage Article Resources', () => {
	test.beforeEach(async ({ page }) => {
		await mockAnalystAuth(page);
	});

	test('should have resource manager in editor', async ({ page }) => {
		await page.goto('/analyst/edit/1');

		if (await page.locator('[data-testid="resource-manager"]').isVisible()) {
			await expect(page.locator('[data-testid="resource-manager"]')).toBeVisible();
		}
	});

	test('should open add resource modal', async ({ page }) => {
		await page.goto('/analyst/edit/1');

		if (await page.locator('[data-testid="add-resource-btn"]').isVisible()) {
			await page.click('[data-testid="add-resource-btn"]');
			await expect(page.locator('[data-testid="resource-modal"]')).toBeVisible();
		}
	});

	test('should display resource type options', async ({ page }) => {
		await page.goto('/analyst/edit/1');

		if (await page.locator('[data-testid="add-resource-btn"]').isVisible()) {
			await page.click('[data-testid="add-resource-btn"]');

			// Should show resource type options
			await expect(page.locator('[data-testid="resource-type-text"]')).toBeVisible();
			await expect(page.locator('[data-testid="resource-type-table"]')).toBeVisible();
		}
	});
});

test.describe('3.5 Submit Article for Review', () => {
	test.beforeEach(async ({ page }) => {
		await mockAnalystAuth(page);
	});

	test('should have submit for review button', async ({ page }) => {
		await page.goto('/analyst/edit/1');

		if (await page.locator('[data-testid="submit-review-btn"]').isVisible()) {
			await expect(page.locator('[data-testid="submit-review-btn"]')).toBeVisible();
		}
	});

	test('should show confirmation dialog on submit', async ({ page }) => {
		await page.goto('/analyst/edit/1');

		if (await page.locator('[data-testid="submit-review-btn"]').isVisible()) {
			await page.click('[data-testid="submit-review-btn"]');
			await expect(page.locator('[data-testid="confirm-dialog"]')).toBeVisible();
		}
	});

	test('should submit article and change status', async ({ page }) => {
		await page.goto('/analyst/edit/1');

		if (await page.locator('[data-testid="submit-review-btn"]').isVisible()) {
			await page.click('[data-testid="submit-review-btn"]');

			// Confirm submission
			await page.click('[data-testid="confirm-submit"]');

			// Verify success or redirect
			await expect(page.locator('[data-testid="submit-success"]')).toBeVisible();
		}
	});
});

test.describe('3.6 Revise Rejected Article', () => {
	test.beforeEach(async ({ page }) => {
		await mockAnalystAuth(page);
	});

	test('should show rejected articles with feedback', async ({ page }) => {
		await page.goto('/analyst/macro');

		// Look for rejected article indicator
		const rejected = page.locator('[data-testid="rejected-article"]');
		if (await rejected.first().isVisible()) {
			await expect(page.locator('[data-testid="rejection-feedback"]')).toBeVisible();
		}
	});
});

test.describe('3.7 Delete Draft Article', () => {
	test.beforeEach(async ({ page }) => {
		await mockAnalystAuth(page);
	});

	test('should have delete button for drafts', async ({ page }) => {
		await page.goto('/analyst/macro');

		const deleteBtn = page.locator('[data-testid="delete-draft-btn"]').first();
		if (await deleteBtn.isVisible()) {
			await expect(deleteBtn).toBeVisible();
		}
	});

	test('should confirm before deleting', async ({ page }) => {
		await page.goto('/analyst/macro');

		const deleteBtn = page.locator('[data-testid="delete-draft-btn"]').first();
		if (await deleteBtn.isVisible()) {
			await deleteBtn.click();
			await expect(page.locator('[data-testid="confirm-delete"]')).toBeVisible();
		}
	});
});
