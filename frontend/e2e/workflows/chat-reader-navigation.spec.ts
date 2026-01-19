import { test, expect } from '@playwright/test';
import { loginAsReader } from '../fixtures/auth';
import { mockChatAPI, sendChatMessage, ensureChatPanelReady, waitForChatNavigation } from '../fixtures/chat';

/**
 * Chat Navigation to Reader Topic Tests
 *
 * These tests specifically verify that chat-based navigation to reader topic pages works.
 * This was identified as a potential issue in the navigation system.
 */

test.describe('Chat Navigation to Reader Topic', () => {
	test.beforeEach(async ({ page }) => {
		await loginAsReader(page);
		await mockChatAPI(page);
	});

	test('should navigate to reader/macro via chat command', async ({ page }) => {
		// Start from home page
		await page.goto('/');
		await page.waitForLoadState('networkidle');

		// Ensure chat panel is ready
		await ensureChatPanelReady(page);

		// Send navigation command
		await sendChatMessage(page, 'show me macro articles');

		// Wait for navigation to complete
		await waitForChatNavigation(page, /\/reader\/macro/);

		// Verify we're on the reader/macro page
		expect(page.url()).toContain('/reader/macro');
	});

	test('should navigate to reader/equity via chat command', async ({ page }) => {
		// Start from home page
		await page.goto('/');
		await page.waitForLoadState('networkidle');

		// Ensure chat panel is ready
		await ensureChatPanelReady(page);

		// Send navigation command
		await sendChatMessage(page, 'go to equity topic');

		// Wait for navigation to complete
		await waitForChatNavigation(page, /\/reader\/equity/);

		// Verify we're on the reader/equity page
		expect(page.url()).toContain('/reader/equity');
	});

	test('should navigate to reader/credit via chat command', async ({ page }) => {
		// Start from home page
		await page.goto('/');
		await page.waitForLoadState('networkidle');

		// Ensure chat panel is ready
		await ensureChatPanelReady(page);

		// Send navigation command
		await sendChatMessage(page, 'show credit articles');

		// Wait for navigation to complete
		await waitForChatNavigation(page, /\/reader\/credit/);

		// Verify we're on the reader/credit page
		expect(page.url()).toContain('/reader/credit');
	});

	test('should navigate from reader/macro to reader/equity via chat', async ({ page }) => {
		// Start from reader/macro page
		await page.goto('/reader/macro');
		await page.waitForLoadState('networkidle');

		// Ensure chat panel is ready
		await ensureChatPanelReady(page);

		// Send navigation command
		await sendChatMessage(page, 'go to equity topic');

		// Wait for navigation to complete
		await waitForChatNavigation(page, /\/reader\/equity/);

		// Verify we're on the reader/equity page
		expect(page.url()).toContain('/reader/equity');
	});

	test('should navigate from search to reader topic via chat', async ({ page }) => {
		// Start from search page
		await page.goto('/reader/search');
		await page.waitForLoadState('networkidle');

		// Ensure chat panel is ready
		await ensureChatPanelReady(page);

		// Send navigation command
		await sendChatMessage(page, 'show me macro articles');

		// Wait for navigation to complete
		await waitForChatNavigation(page, /\/reader\/macro/);

		// Verify we're on the reader/macro page
		expect(page.url()).toContain('/reader/macro');
	});
});
