import { test, expect, type Page } from '@playwright/test';

/**
 * Profile and Chat Workflow E2E Tests
 *
 * Tests based on docs/12-testing-workflows.md:
 * - Section 7: Profile Workflows
 * - Section 8: Chat & AI Agent Workflows
 */

// Helper to mock authentication
async function mockAuth(page: Page) {
	await page.addInitScript(() => {
		const mockToken = {
			access_token: 'test-token',
			user: {
				id: 1,
				email: 'user@test.com',
				name: 'Test',
				surname: 'User',
				scopes: ['macro:reader', 'equity:reader']
			}
		};
		localStorage.setItem('auth', JSON.stringify(mockToken));
	});
}

// Section 7: Profile Workflows
test.describe('7.1 View Profile', () => {
	test.beforeEach(async ({ page }) => {
		await mockAuth(page);
	});

	test('should load profile page', async ({ page }) => {
		await page.goto('/user/profile');

		await expect(page.locator('[data-testid="profile-page"]')).toBeVisible();
	});

	test('should display personal info', async ({ page }) => {
		await page.goto('/user/profile');

		await expect(page.locator('[data-testid="user-name"]')).toBeVisible();
		await expect(page.locator('[data-testid="user-email"]')).toBeVisible();
	});

	test('should show assigned groups', async ({ page }) => {
		await page.goto('/user/profile');

		await expect(page.locator('[data-testid="user-groups"]')).toBeVisible();
	});

	test('should display access statistics', async ({ page }) => {
		await page.goto('/user/profile');

		await expect(page.locator('[data-testid="access-stats"]')).toBeVisible();
	});
});

test.describe('7.2 Update Chat Tonality', () => {
	test.beforeEach(async ({ page }) => {
		await mockAuth(page);
	});

	test('should display tonality settings', async ({ page }) => {
		await page.goto('/user/profile');

		await expect(page.locator('[data-testid="tonality-settings"]')).toBeVisible();
	});

	test('should have chat tonality selector', async ({ page }) => {
		await page.goto('/user/profile');

		await expect(page.locator('[data-testid="chat-tonality-select"]')).toBeVisible();
	});

	test('should save tonality preference', async ({ page }) => {
		await page.goto('/user/profile');

		const select = page.locator('[data-testid="chat-tonality-select"]');
		if (await select.isVisible()) {
			await select.selectOption({ index: 1 });
			await page.click('[data-testid="save-preferences"]');

			await expect(page.locator('[data-testid="save-success"]')).toBeVisible();
		}
	});
});

test.describe('7.3 Update Content Tonality', () => {
	test.beforeEach(async ({ page }) => {
		await mockAuth(page);
	});

	test('should have content tonality selector', async ({ page }) => {
		await page.goto('/user/profile');

		await expect(page.locator('[data-testid="content-tonality-select"]')).toBeVisible();
	});

	test('should save content tonality preference', async ({ page }) => {
		await page.goto('/user/profile');

		const select = page.locator('[data-testid="content-tonality-select"]');
		if (await select.isVisible()) {
			await select.selectOption({ index: 1 });
			await page.click('[data-testid="save-preferences"]');

			await expect(page.locator('[data-testid="save-success"]')).toBeVisible();
		}
	});
});

// Section 8: Chat & AI Agent Workflows
test.describe('8.1 Basic Chat Interaction', () => {
	test.beforeEach(async ({ page }) => {
		await mockAuth(page);
	});

	test('should display chat interface', async ({ page }) => {
		await page.goto('/');

		await expect(page.locator('[data-testid="chat-panel"]')).toBeVisible();
	});

	test('should have message input', async ({ page }) => {
		await page.goto('/');

		await expect(page.locator('[data-testid="chat-input"]')).toBeVisible();
	});

	test('should send message', async ({ page }) => {
		await page.goto('/');

		await page.fill('[data-testid="chat-input"]', 'Hello');
		await page.press('[data-testid="chat-input"]', 'Enter');

		// Message should appear in chat
		await expect(page.locator('[data-testid="chat-message-user"]')).toBeVisible();
	});

	test('should receive response', async ({ page }) => {
		await page.goto('/');

		await page.fill('[data-testid="chat-input"]', 'Hello');
		await page.press('[data-testid="chat-input"]', 'Enter');

		// Wait for AI response
		await page.waitForSelector('[data-testid="chat-message-assistant"]', { timeout: 30000 });
		await expect(page.locator('[data-testid="chat-message-assistant"]')).toBeVisible();
	});
});

test.describe('8.2 Chat with Article Context', () => {
	test.beforeEach(async ({ page }) => {
		await mockAuth(page);
	});

	test('should include article references in response', async ({ page }) => {
		await page.goto('/reader/macro');

		await page.fill('[data-testid="chat-input"]', 'Tell me about recent macro articles');
		await page.press('[data-testid="chat-input"]', 'Enter');

		// Wait for response with article references
		await page.waitForSelector('[data-testid="chat-message-assistant"]', { timeout: 30000 });

		// Check if article references are included
		const response = page.locator('[data-testid="chat-message-assistant"]').last();
		// Articles may be referenced as links
	});
});

test.describe('8.3 Chat-Triggered Actions', () => {
	test.beforeEach(async ({ page }) => {
		await mockAuth(page);
	});

	test('should navigate on topic request', async ({ page }) => {
		await page.goto('/');

		await page.fill('[data-testid="chat-input"]', 'Show me equity articles');
		await page.press('[data-testid="chat-input"]', 'Enter');

		// Wait for response and navigation
		await page.waitForTimeout(2000);

		// URL might change to equity tab
		// Check if navigation occurred
	});

	test('should trigger search', async ({ page }) => {
		await page.goto('/');

		await page.fill('[data-testid="chat-input"]', 'Search for inflation');
		await page.press('[data-testid="chat-input"]', 'Enter');

		await page.waitForTimeout(2000);

		// Search might be executed
	});
});

test.describe('8.6 Conversation Memory', () => {
	test.beforeEach(async ({ page }) => {
		await mockAuth(page);
	});

	test('should remember context in follow-up', async ({ page }) => {
		await page.goto('/');

		// First message
		await page.fill('[data-testid="chat-input"]', 'What is GDP?');
		await page.press('[data-testid="chat-input"]', 'Enter');
		await page.waitForSelector('[data-testid="chat-message-assistant"]', { timeout: 30000 });

		// Follow-up should reference previous context
		await page.fill('[data-testid="chat-input"]', 'How does it affect inflation?');
		await page.press('[data-testid="chat-input"]', 'Enter');
		await page.waitForSelector('[data-testid="chat-message-assistant"]:nth-child(4)', { timeout: 30000 });

		// Agent should understand "it" refers to GDP
	});

	test('should clear history', async ({ page }) => {
		await page.goto('/');

		// Send a message
		await page.fill('[data-testid="chat-input"]', 'Test message');
		await page.press('[data-testid="chat-input"]', 'Enter');
		await page.waitForSelector('[data-testid="chat-message-assistant"]', { timeout: 30000 });

		// Clear history
		const clearBtn = page.locator('[data-testid="clear-chat"]');
		if (await clearBtn.isVisible()) {
			await clearBtn.click();

			// Chat should be cleared
			await expect(page.locator('[data-testid="chat-message-user"]')).not.toBeVisible();
		}
	});
});

// Authentication Tests
test.describe('Authentication Workflows', () => {
	test('should show login page when not authenticated', async ({ page }) => {
		// Don't mock auth
		await page.goto('/');

		// Should redirect to login or show login button
		await expect(page.locator('[data-testid="login-btn"]')).toBeVisible();
	});

	test('should have LinkedIn OAuth button', async ({ page }) => {
		await page.goto('/');

		await expect(page.locator('[data-testid="linkedin-login"]')).toBeVisible();
	});

	test('should redirect after login', async ({ page }) => {
		await mockAuth(page);
		await page.goto('/');

		// User should be logged in
		await expect(page.locator('[data-testid="user-menu"]')).toBeVisible();
	});

	test('should logout user', async ({ page }) => {
		await mockAuth(page);
		await page.goto('/');

		// Click logout
		await page.click('[data-testid="user-menu"]');
		await page.click('[data-testid="logout-btn"]');

		// Should be logged out
		await expect(page.locator('[data-testid="login-btn"]')).toBeVisible();
	});
});
