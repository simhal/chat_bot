import { test, expect } from '@playwright/test';
import {
	loginAsReader,
	loginAsAnalyst,
	loginAsEditor,
	loginAsTopicAdmin,
	loginAsGlobalAdmin
} from '../fixtures/auth';
import {
	mockChatAPI,
	sendChatMessage,
	getLastAssistantMessage,
	waitForChatNavigation,
	ensureChatPanelReady,
	buildNavigationResponse,
	mockChatWithResponses
} from '../fixtures/chat';

/**
 * Chat Navigation E2E Tests
 *
 * Tests that verify users can navigate to different sections of the application
 * using natural language chat commands. These tests validate the v2 agent build's
 * navigation handling where:
 *
 * 1. Navigation intent is ALWAYS routed to navigation_node (priority 1)
 * 2. Permission check is on the TARGET section, not current section
 * 3. Users can say "go home" from ANY page and it works
 */

// =============================================================================
// Basic Navigation Tests (Any User)
// =============================================================================

test.describe('Chat Navigation - Basic (Reader)', () => {
	test.beforeEach(async ({ page }) => {
		await loginAsReader(page);
		await mockChatAPI(page);
	});

	test('should navigate to home from any page', async ({ page }) => {
		// Start on profile page
		await page.goto('/user/profile');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'go home');

		const response = await getLastAssistantMessage(page);
		expect(response).toContain('home');
		await waitForChatNavigation(page, '/');
	});

	test('should navigate to search', async ({ page }) => {
		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'go to search');

		const response = await getLastAssistantMessage(page);
		expect(response).toContain('search');
		await waitForChatNavigation(page, '/reader/search');
	});

	test('should navigate to profile', async ({ page }) => {
		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'show my profile');

		const response = await getLastAssistantMessage(page);
		expect(response).toContain('profile');
		await waitForChatNavigation(page, '/user/profile');
	});

	test('should navigate to settings', async ({ page }) => {
		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'open settings');

		const response = await getLastAssistantMessage(page);
		expect(response).toContain('settings');
		await waitForChatNavigation(page, '/user/settings');
	});

	test('should navigate to specific topic', async ({ page }) => {
		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'show me macro articles');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('macro');
		await waitForChatNavigation(page, '/reader/macro');
	});

	test('should show active state in header after topic navigation', async ({ page }) => {
		// Navigate to a specific topic via chat
		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'go to macro');

		await waitForChatNavigation(page, '/reader/macro');

		// Verify the Macro topic tab is highlighted as active in the header
		const macroTab = page.locator('.topic-nav a[href="/reader/macro"]');
		await expect(macroTab).toHaveClass(/active/);

		// Verify other topic tabs are NOT active
		const equityTab = page.locator('.topic-nav a[href="/reader/equity"]');
		await expect(equityTab).not.toHaveClass(/active/);
	});

	test('should show active state for search tab', async ({ page }) => {
		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'go to search');

		await waitForChatNavigation(page, '/reader/search');

		// Verify Search tab is active
		const searchTab = page.locator('.topic-nav a[href="/reader/search"]');
		await expect(searchTab).toHaveClass(/active/);
	});

	test('should navigate home from deep page', async ({ page }) => {
		// Start on settings page (deep in user section)
		await page.goto('/user/settings');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'take me home');

		await waitForChatNavigation(page, '/');
	});
});

// =============================================================================
// Analyst Navigation Tests
// =============================================================================

test.describe('Chat Navigation - Analyst Role', () => {
	test.beforeEach(async ({ page }) => {
		await loginAsAnalyst(page);
		await mockChatAPI(page);
	});

	test('should navigate to analyst dashboard', async ({ page }) => {
		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'go to analyst');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('analyst');
		await waitForChatNavigation(page, /\/analyst\//);
	});

	test('should navigate to analyst from reader view', async ({ page }) => {
		await page.goto('/reader/macro');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'open analyst dashboard');

		await waitForChatNavigation(page, /\/analyst\//);
	});

	test('should navigate home from analyst editor', async ({ page }) => {
		// Simulate being in analyst editor
		await page.goto('/analyst/macro');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'go home');

		await waitForChatNavigation(page, '/');
	});

	test('should switch between analyst topics via chat', async ({ page }) => {
		await page.goto('/analyst/macro');
		await ensureChatPanelReady(page);

		// Mock response for equity navigation
		await mockChatWithResponses(page, [
			{
				trigger: 'switch to equity',
				response: buildNavigationResponse('analyst_dashboard', 'equity', 'Switching to equity analyst dashboard.')
			}
		]);

		await sendChatMessage(page, 'switch to equity');

		await waitForChatNavigation(page, '/analyst/equity');
	});
});

// =============================================================================
// Editor Navigation Tests
// =============================================================================

test.describe('Chat Navigation - Editor Role', () => {
	test.beforeEach(async ({ page }) => {
		await loginAsEditor(page);
		await mockChatAPI(page);
	});

	test('should navigate to editor dashboard', async ({ page }) => {
		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'go to editor');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('editor');
		await waitForChatNavigation(page, /\/editor\//);
	});

	test('should navigate to review queue', async ({ page }) => {
		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'show review queue');

		await waitForChatNavigation(page, /\/editor\//);
	});

	test('should navigate home from editor dashboard', async ({ page }) => {
		await page.goto('/editor/macro');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'go home');

		await waitForChatNavigation(page, '/');
	});

	test('should navigate to analyst from editor', async ({ page }) => {
		// Editors also have analyst access
		await page.goto('/editor/macro');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'go to analyst');

		await waitForChatNavigation(page, /\/analyst\//);
	});
});

// =============================================================================
// Topic Admin Navigation Tests
// =============================================================================

test.describe('Chat Navigation - Topic Admin Role', () => {
	test.beforeEach(async ({ page }) => {
		await loginAsTopicAdmin(page);
		await mockChatAPI(page);
	});

	test('should navigate to admin panel', async ({ page }) => {
		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'go to admin');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('admin');
		await waitForChatNavigation(page, /\/admin\//);
	});

	test('should navigate to manage articles', async ({ page }) => {
		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'manage articles');

		await waitForChatNavigation(page, /\/admin\/.*\/articles/);
	});

	test('should navigate home from admin', async ({ page }) => {
		await page.goto('/admin/macro/articles');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'go home');

		await waitForChatNavigation(page, '/');
	});

	test('should navigate between admin sections', async ({ page }) => {
		await page.goto('/admin/macro/articles');
		await ensureChatPanelReady(page);

		// Mock response for resources navigation
		await mockChatWithResponses(page, [
			{
				trigger: 'show resources',
				response: buildNavigationResponse('admin_resources', 'macro', 'Opening admin resources.')
			}
		]);

		await sendChatMessage(page, 'show resources');

		await waitForChatNavigation(page, '/admin/macro/resources');
	});
});

// =============================================================================
// Global Admin Navigation Tests
// =============================================================================

test.describe('Chat Navigation - Global Admin Role', () => {
	test.beforeEach(async ({ page }) => {
		await loginAsGlobalAdmin(page);
		await mockChatAPI(page);
	});

	test('should navigate to user management', async ({ page }) => {
		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'manage users');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toMatch(/user|management/);
		await waitForChatNavigation(page, '/root/users');
	});

	test('should navigate to topic management', async ({ page }) => {
		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'manage topics');

		await waitForChatNavigation(page, '/root/topics');
	});

	test('should navigate to global admin', async ({ page }) => {
		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'go to global admin');

		await waitForChatNavigation(page, /\/root\//);
	});

	test('should navigate home from root admin', async ({ page }) => {
		await page.goto('/root/users');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'go home');

		await waitForChatNavigation(page, '/');
	});

	test('should switch between root sections', async ({ page }) => {
		await page.goto('/root/users');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'open topic management');

		await waitForChatNavigation(page, '/root/topics');
	});
});

// =============================================================================
// Permission Boundary Tests
// =============================================================================

test.describe('Chat Navigation - Permission Boundaries', () => {
	test('reader should not navigate to analyst dashboard', async ({ page }) => {
		await loginAsReader(page);
		await mockChatWithResponses(page, [
			{
				trigger: 'go to analyst',
				response: {
					response_text: 'You need analyst access on at least one topic.',
					conversation_id: 'test'
				}
			}
		]);

		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'go to analyst');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('need');
		// Should NOT navigate
		await expect(page).toHaveURL('/');
	});

	test('reader should not navigate to admin', async ({ page }) => {
		await loginAsReader(page);
		await mockChatWithResponses(page, [
			{
				trigger: 'go to admin',
				response: {
					response_text: 'You need admin access on at least one topic.',
					conversation_id: 'test'
				}
			}
		]);

		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'go to admin');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('need');
		await expect(page).toHaveURL('/');
	});

	test('topic admin should not navigate to global admin', async ({ page }) => {
		await loginAsTopicAdmin(page);
		await mockChatWithResponses(page, [
			{
				trigger: 'manage users',
				response: {
					response_text: 'You need global admin access for this area.',
					conversation_id: 'test'
				}
			}
		]);

		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'manage users');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('global admin');
		await expect(page).toHaveURL('/');
	});
});

// =============================================================================
// Navigation from Deep Pages Tests
// =============================================================================

test.describe('Chat Navigation - From Deep Pages', () => {
	test.beforeEach(async ({ page }) => {
		await loginAsAnalyst(page);
		await mockChatAPI(page);
	});

	test('should navigate home from article editor', async ({ page }) => {
		// Simulate being in article editor (deep page)
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'go home');

		await waitForChatNavigation(page, '/');
	});

	test('should navigate to search from article editor', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'go to search');

		await waitForChatNavigation(page, '/reader/search');
	});

	test('should navigate to profile from article editor', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'show my profile');

		await waitForChatNavigation(page, '/user/profile');
	});

	test('should navigate to settings from any page', async ({ page }) => {
		await page.goto('/analyst/macro');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'open settings');

		await waitForChatNavigation(page, '/user/settings');
	});
});

// =============================================================================
// Natural Language Variations Tests
// =============================================================================

test.describe('Chat Navigation - Natural Language Variations', () => {
	test.beforeEach(async ({ page }) => {
		await loginAsAnalyst(page);
		await mockChatAPI(page);
	});

	test('should understand "take me to" phrasing', async ({ page }) => {
		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'take me home');

		await waitForChatNavigation(page, '/');
	});

	test('should understand "show me" phrasing', async ({ page }) => {
		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'show my profile');

		await waitForChatNavigation(page, '/user/profile');
	});

	test('should understand "open" phrasing', async ({ page }) => {
		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'open settings');

		await waitForChatNavigation(page, '/user/settings');
	});

	test('should understand topic requests', async ({ page }) => {
		await page.goto('/');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'show me macro articles');

		await waitForChatNavigation(page, '/reader/macro');
	});
});

// =============================================================================
// Chat Panel Visibility Tests
// =============================================================================

test.describe('Chat Navigation - Panel Availability', () => {
	test('chat panel should be visible on home page', async ({ page }) => {
		await loginAsReader(page);
		await page.goto('/');
		await ensureChatPanelReady(page);

		await expect(page.locator('[data-testid="chat-panel"]')).toBeVisible();
		await expect(page.locator('[data-testid="chat-input"]')).toBeVisible();
	});

	test('chat panel should be visible on reader page', async ({ page }) => {
		await loginAsReader(page);
		await page.goto('/reader/macro');
		await ensureChatPanelReady(page);

		await expect(page.locator('[data-testid="chat-panel"]')).toBeVisible();
	});

	test('chat panel should be visible on analyst page', async ({ page }) => {
		await loginAsAnalyst(page);
		await page.goto('/analyst/macro');
		await ensureChatPanelReady(page);

		await expect(page.locator('[data-testid="chat-panel"]')).toBeVisible();
	});

	test('chat panel should be visible on admin page', async ({ page }) => {
		await loginAsTopicAdmin(page);
		await page.goto('/admin/macro/articles');
		await ensureChatPanelReady(page);

		await expect(page.locator('[data-testid="chat-panel"]')).toBeVisible();
	});
});
