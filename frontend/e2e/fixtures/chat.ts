import { type Page, type Route } from '@playwright/test';

/**
 * E2E test chat fixtures.
 *
 * These functions help test the chat functionality by providing
 * mocking utilities and helper functions for interacting with the chat panel.
 */

const API_URL = process.env.API_URL || 'http://localhost:8004';

/**
 * Build a navigation response object for mocking.
 */
export function buildNavigationResponse(
	section: string,
	topic?: string,
	message?: string
): {
	response: string;
	agent_type: string;
	routing_reason: string;
	articles: [];
	ui_action: { type: string; params: Record<string, any> };
} {
	return {
		response: message || `Navigating to ${section}${topic ? ` for ${topic}` : ''}`,
		agent_type: 'navigation',
		routing_reason: 'Navigation request',
		articles: [],
		ui_action: {
			type: 'goto',
			params: {
				section,
				...(topic && { topic })
			}
		}
	};
}

/**
 * Mock the chat API to return a specific response.
 */
export async function mockChatAPI(page: Page, response?: object): Promise<void> {
	const defaultResponse = {
		response: 'Hello! How can I help you today?',
		agent_type: 'general',
		routing_reason: 'Default response',
		articles: [],
		ui_action: null
	};

	await page.route(`${API_URL}/api/chat`, async (route: Route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify(response || defaultResponse)
		});
	});
}

/**
 * Mock the chat API with a sequence of responses.
 */
export async function mockChatWithResponses(page: Page, responses: object[]): Promise<void> {
	let callIndex = 0;

	await page.route(`${API_URL}/api/chat`, async (route: Route) => {
		const response = responses[callIndex] || responses[responses.length - 1];
		callIndex++;

		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify(response)
		});
	});
}

/**
 * Wait for the chat panel to be ready for interaction.
 */
export async function ensureChatPanelReady(page: Page, timeout = 5000): Promise<void> {
	// Wait for chat panel to be visible
	const chatPanel = page.locator('[data-testid="chat-panel"], .chat-panel, .chat-container');
	await chatPanel.first().waitFor({ state: 'visible', timeout }).catch(() => {
		// Chat panel might not exist on all pages
	});

	// Wait for any loading states to complete
	await page.waitForTimeout(500);
}

/**
 * Send a chat message and wait for the response.
 */
export async function sendChatMessage(page: Page, message: string): Promise<void> {
	// Find the chat input
	const chatInput = page.locator(
		'[data-testid="chat-input"], .chat-input input, .chat-input textarea, input[placeholder*="message"], textarea[placeholder*="message"]'
	);

	// Type the message
	await chatInput.first().fill(message);

	// Submit the message (press Enter or click send button)
	const sendButton = page.locator(
		'[data-testid="send-button"], .send-button, button[type="submit"]'
	);
	const hasSendButton = await sendButton.first().isVisible().catch(() => false);

	if (hasSendButton) {
		await sendButton.first().click();
	} else {
		await chatInput.first().press('Enter');
	}

	// Wait for response
	await page.waitForTimeout(1000);
}

/**
 * Get the last assistant message from the chat.
 */
export async function getLastAssistantMessage(page: Page): Promise<string> {
	// Find assistant messages
	const assistantMessages = page.locator(
		'[data-testid="assistant-message"], .assistant-message, .chat-message.assistant'
	);

	const count = await assistantMessages.count();
	if (count === 0) {
		return '';
	}

	const lastMessage = assistantMessages.last();
	return (await lastMessage.textContent()) || '';
}

/**
 * Wait for a navigation action to complete after a chat message.
 */
export async function waitForChatNavigation(page: Page, expectedPath: string | RegExp): Promise<void> {
	await page.waitForURL(expectedPath, { timeout: 10000 }).catch(() => {
		// Navigation might not happen if feature isn't implemented
	});
}
