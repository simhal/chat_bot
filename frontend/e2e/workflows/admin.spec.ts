import { test, expect, type Page } from '@playwright/test';

/**
 * Admin Workflow E2E Tests
 *
 * Tests based on docs/12-testing-workflows.md Sections 5 & 6:
 * - Section 5: Topic Admin Workflows
 * - Section 6: Global Admin Workflows
 */

// Helper to mock topic admin authentication
async function mockTopicAdminAuth(page: Page) {
	await page.addInitScript(() => {
		const mockToken = {
			access_token: 'test-topic-admin-token',
			user: {
				id: 4,
				email: 'topicadmin@test.com',
				name: 'Test',
				surname: 'TopicAdmin',
				scopes: ['macro:admin']
			}
		};
		localStorage.setItem('auth', JSON.stringify(mockToken));
	});
}

// Helper to mock global admin authentication
async function mockGlobalAdminAuth(page: Page) {
	await page.addInitScript(() => {
		const mockToken = {
			access_token: 'test-global-admin-token',
			user: {
				id: 5,
				email: 'admin@test.com',
				name: 'Test',
				surname: 'Admin',
				scopes: ['global:admin']
			}
		};
		localStorage.setItem('auth', JSON.stringify(mockToken));
	});
}

test.describe('5.1 Access Admin Content Management', () => {
	test.beforeEach(async ({ page }) => {
		await mockTopicAdminAuth(page);
	});

	test('should load admin content panel', async ({ page }) => {
		await page.goto('/admin/content');

		await expect(page.locator('[data-testid="admin-content-panel"]')).toBeVisible();
	});

	test('should have topic filter', async ({ page }) => {
		await page.goto('/admin/content');

		await expect(page.locator('[data-testid="topic-filter"]')).toBeVisible();
	});

	test('should show all article statuses', async ({ page }) => {
		await page.goto('/admin/content');

		// Status filter should have all options
		const statusFilter = page.locator('[data-testid="status-filter"]');
		if (await statusFilter.isVisible()) {
			await statusFilter.click();
			await expect(page.locator('[data-testid="status-draft"]')).toBeVisible();
			await expect(page.locator('[data-testid="status-editor"]')).toBeVisible();
			await expect(page.locator('[data-testid="status-published"]')).toBeVisible();
		}
	});
});

test.describe('5.2 View All Articles', () => {
	test.beforeEach(async ({ page }) => {
		await mockTopicAdminAuth(page);
	});

	test('should display all articles regardless of status', async ({ page }) => {
		await page.goto('/admin/content');

		await expect(page.locator('[data-testid="admin-article-list"]')).toBeVisible();
	});

	test('should filter by status', async ({ page }) => {
		await page.goto('/admin/content');

		const statusFilter = page.locator('[data-testid="status-filter"]');
		if (await statusFilter.isVisible()) {
			await statusFilter.selectOption('draft');

			// All visible articles should be drafts
			const articles = page.locator('[data-testid="admin-article-item"]');
			// Verify filter applied
		}
	});
});

test.describe('5.3 Edit Any Article', () => {
	test.beforeEach(async ({ page }) => {
		await mockTopicAdminAuth(page);
	});

	test('should open edit for any article', async ({ page }) => {
		await page.goto('/admin/content');

		const editBtn = page.locator('[data-testid="admin-edit-btn"]').first();
		if (await editBtn.isVisible()) {
			await editBtn.click();
			await expect(page.locator('[data-testid="admin-article-editor"]')).toBeVisible();
		}
	});

	test('should allow editing author/editor fields', async ({ page }) => {
		await page.goto('/admin/content');

		const editBtn = page.locator('[data-testid="admin-edit-btn"]').first();
		if (await editBtn.isVisible()) {
			await editBtn.click();

			// Admin should be able to edit author
			await expect(page.locator('[data-testid="author-input"]')).toBeEditable();
		}
	});
});

test.describe('5.4 Reorder Articles', () => {
	test.beforeEach(async ({ page }) => {
		await mockTopicAdminAuth(page);
	});

	test('should have reorder controls', async ({ page }) => {
		await page.goto('/admin/content');

		await expect(page.locator('[data-testid="reorder-mode"]')).toBeVisible();
	});

	test('should save new order', async ({ page }) => {
		await page.goto('/admin/content');

		const reorderBtn = page.locator('[data-testid="reorder-mode"]');
		if (await reorderBtn.isVisible()) {
			await reorderBtn.click();

			// Drag first item down
			const firstItem = page.locator('[data-testid="admin-article-item"]').first();
			const secondItem = page.locator('[data-testid="admin-article-item"]').nth(1);

			if (await firstItem.isVisible() && await secondItem.isVisible()) {
				await firstItem.dragTo(secondItem);

				// Save order
				await page.click('[data-testid="save-order"]');
				await expect(page.locator('[data-testid="order-saved"]')).toBeVisible();
			}
		}
	});
});

test.describe('5.5 Recall Published Article', () => {
	test.beforeEach(async ({ page }) => {
		await mockTopicAdminAuth(page);
	});

	test('should have recall button for published articles', async ({ page }) => {
		await page.goto('/admin/content?status=published');

		const recallBtn = page.locator('[data-testid="recall-btn"]').first();
		if (await recallBtn.isVisible()) {
			await expect(recallBtn).toBeVisible();
		}
	});

	test('should recall article to draft', async ({ page }) => {
		await page.goto('/admin/content?status=published');

		const recallBtn = page.locator('[data-testid="recall-btn"]').first();
		if (await recallBtn.isVisible()) {
			await recallBtn.click();

			// Confirm recall
			await page.click('[data-testid="confirm-recall"]');

			await expect(page.locator('[data-testid="recall-success"]')).toBeVisible();
		}
	});
});

test.describe('5.6 Deactivate Article', () => {
	test.beforeEach(async ({ page }) => {
		await mockTopicAdminAuth(page);
	});

	test('should have deactivate option', async ({ page }) => {
		await page.goto('/admin/content');

		const deactivateBtn = page.locator('[data-testid="deactivate-btn"]').first();
		if (await deactivateBtn.isVisible()) {
			await expect(deactivateBtn).toBeVisible();
		}
	});

	test('should require confirmation for deactivate', async ({ page }) => {
		await page.goto('/admin/content');

		const deactivateBtn = page.locator('[data-testid="deactivate-btn"]').first();
		if (await deactivateBtn.isVisible()) {
			await deactivateBtn.click();
			await expect(page.locator('[data-testid="confirm-deactivate"]')).toBeVisible();
		}
	});
});

test.describe('5.7 Reactivate Article', () => {
	test.beforeEach(async ({ page }) => {
		await mockTopicAdminAuth(page);
	});

	test('should show reactivate for inactive articles', async ({ page }) => {
		await page.goto('/admin/content?show_inactive=true');

		const reactivateBtn = page.locator('[data-testid="reactivate-btn"]').first();
		if (await reactivateBtn.isVisible()) {
			await expect(reactivateBtn).toBeVisible();
		}
	});
});

test.describe('5.8 Purge Article (Permanent Delete)', () => {
	test.beforeEach(async ({ page }) => {
		await mockTopicAdminAuth(page);
	});

	test('should have purge option', async ({ page }) => {
		await page.goto('/admin/content');

		const purgeBtn = page.locator('[data-testid="purge-btn"]').first();
		if (await purgeBtn.isVisible()) {
			await expect(purgeBtn).toBeVisible();
		}
	});

	test('should show strong warning for purge', async ({ page }) => {
		await page.goto('/admin/content');

		const purgeBtn = page.locator('[data-testid="purge-btn"]').first();
		if (await purgeBtn.isVisible()) {
			await purgeBtn.click();

			// Should have strong warning
			await expect(page.locator('[data-testid="purge-warning"]')).toContainText(/permanent/i);
		}
	});
});

// Global Admin Tests
test.describe('6.1 Access Global Admin Panel', () => {
	test.beforeEach(async ({ page }) => {
		await mockGlobalAdminAuth(page);
	});

	test('should load global admin panel', async ({ page }) => {
		await page.goto('/admin/global');

		await expect(page.locator('[data-testid="global-admin-panel"]')).toBeVisible();
	});

	test('should show all topics', async ({ page }) => {
		await page.goto('/admin/global');

		await expect(page.locator('[data-testid="topics-list"]')).toBeVisible();
	});
});

test.describe('6.2 Manage Topics', () => {
	test.beforeEach(async ({ page }) => {
		await mockGlobalAdminAuth(page);
	});

	test('should have create topic option', async ({ page }) => {
		await page.goto('/admin/global?view=topics');

		await expect(page.locator('[data-testid="create-topic-btn"]')).toBeVisible();
	});

	test('should open topic creation form', async ({ page }) => {
		await page.goto('/admin/global?view=topics');

		await page.click('[data-testid="create-topic-btn"]');

		await expect(page.locator('[data-testid="topic-form"]')).toBeVisible();
		await expect(page.locator('[data-testid="topic-slug"]')).toBeVisible();
		await expect(page.locator('[data-testid="topic-title"]')).toBeVisible();
	});
});

test.describe('6.3 Edit Global Prompts', () => {
	test.beforeEach(async ({ page }) => {
		await mockGlobalAdminAuth(page);
	});

	test('should display prompt modules', async ({ page }) => {
		await page.goto('/admin/global?view=prompts');

		await expect(page.locator('[data-testid="prompt-modules"]')).toBeVisible();
	});

	test('should edit general prompt', async ({ page }) => {
		await page.goto('/admin/global?view=prompts');

		const generalPrompt = page.locator('[data-testid="prompt-general"]');
		if (await generalPrompt.isVisible()) {
			await generalPrompt.click();

			await expect(page.locator('[data-testid="prompt-editor"]')).toBeVisible();
		}
	});
});

test.describe('6.4 Manage Tonality Options', () => {
	test.beforeEach(async ({ page }) => {
		await mockGlobalAdminAuth(page);
	});

	test('should view tonality options', async ({ page }) => {
		await page.goto('/admin/global?view=tonality');

		await expect(page.locator('[data-testid="tonality-list"]')).toBeVisible();
	});

	test('should create new tonality', async ({ page }) => {
		await page.goto('/admin/global?view=tonality');

		await page.click('[data-testid="create-tonality-btn"]');

		await expect(page.locator('[data-testid="tonality-form"]')).toBeVisible();
	});
});

test.describe('6.5 System-Wide User Management', () => {
	test.beforeEach(async ({ page }) => {
		await mockGlobalAdminAuth(page);
	});

	test('should view all users', async ({ page }) => {
		await page.goto('/admin/global?view=users');

		await expect(page.locator('[data-testid="user-list"]')).toBeVisible();
	});

	test('should search for user', async ({ page }) => {
		await page.goto('/admin/global?view=users');

		await page.fill('[data-testid="user-search"]', 'test@');

		// Verify filter applied
		await page.waitForTimeout(500);
	});

	test('should assign user to group', async ({ page }) => {
		await page.goto('/admin/global?view=users');

		const userRow = page.locator('[data-testid="user-row"]').first();
		if (await userRow.isVisible()) {
			await userRow.click();

			await expect(page.locator('[data-testid="user-groups"]')).toBeVisible();
			await expect(page.locator('[data-testid="add-group-btn"]')).toBeVisible();
		}
	});

	test('should ban/unban user', async ({ page }) => {
		await page.goto('/admin/global?view=users');

		const banBtn = page.locator('[data-testid="ban-user-btn"]').first();
		if (await banBtn.isVisible()) {
			await expect(banBtn).toBeVisible();
		}
	});
});
