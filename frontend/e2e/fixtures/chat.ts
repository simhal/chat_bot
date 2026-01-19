import { type Page, type Route } from '@playwright/test';

/**
 * Chat API mocking fixtures for E2E testing.
 *
 * These fixtures allow testing chat-triggered navigation and content editing
 * without requiring a live backend. The mock responses simulate the v2 agent
 * build's behavior including UI actions and editor content.
 */

// =============================================================================
// Types
// =============================================================================

export interface ChatMessage {
	role: 'user' | 'assistant';
	content: string;
}

export interface MockUIAction {
	type: string;
	params: Record<string, any>;
}

export interface MockEditorContent {
	headline?: string;
	content?: string;
	keywords?: string;
	article_id?: number;
	action?: string;
	timestamp?: string;
}

export interface MockChatResponse {
	response: string;
	ui_action?: MockUIAction;
	editor_content?: MockEditorContent;
	conversation_id?: string;
	sources?: any[];
}

// =============================================================================
// Mock Response Builders
// =============================================================================

/**
 * Build a navigation response with goto action
 */
export function buildNavigationResponse(
	section: string,
	topic?: string,
	message?: string
): MockChatResponse {
	const sectionDisplayNames: Record<string, string> = {
		home: 'home',
		reader_search: 'search',
		reader_topic: 'reader topic view',
		analyst_dashboard: 'analyst dashboard',
		analyst_editor: 'article editor',
		editor_dashboard: 'editor review queue',
		admin_articles: 'admin articles',
		admin_resources: 'admin resources',
		root_users: 'user management',
		root_topics: 'topic management',
		user_profile: 'your profile',
		user_settings: 'your settings'
	};

	const displayName = sectionDisplayNames[section] || section.replace('_', ' ');
	const topicText = topic ? ` for ${topic}` : '';

	return {
		response: message || `Taking you to ${displayName}${topicText}.`,
		ui_action: {
			type: 'goto',
			params: {
				section,
				...(topic && { topic })
			}
		},
		conversation_id: 'test-conv-id'
	};
}

/**
 * Build a content generation response
 */
export function buildContentResponse(
	action: 'create' | 'regenerate_headline' | 'regenerate_keywords' | 'regenerate_content' | 'edit_section' | 'refine_content',
	content: Partial<MockEditorContent>,
	message?: string
): MockChatResponse {
	const actionMessages: Record<string, string> = {
		create: `I've drafted a new article.\n\n**Headline:** ${content.headline || 'Untitled'}\n**Word count:** ~${(content.content || '').split(' ').length} words`,
		regenerate_headline: `I've generated a new headline:\n\n**${content.headline}**`,
		regenerate_keywords: `I've generated new keywords:\n\n**${content.keywords}**`,
		regenerate_content: `I've rewritten the article content.\n\n**Word count:** ~${(content.content || '').split(' ').length} words`,
		edit_section: `I've edited the **requested section**.\n\n**Word count:** ~${(content.content || '').split(' ').length} words`,
		refine_content: `I've applied your requested changes to the article.\n\n**Word count:** ~${(content.content || '').split(' ').length} words`
	};

	const actionToEditorAction: Record<string, string> = {
		create: 'fill',
		regenerate_headline: 'update_headline',
		regenerate_keywords: 'update_keywords',
		regenerate_content: 'update_content',
		edit_section: 'update_content',
		refine_content: 'update_content'
	};

	return {
		response: message || actionMessages[action],
		editor_content: {
			headline: content.headline || 'Generated Headline',
			content: content.content || 'Generated content goes here.',
			keywords: content.keywords || 'keyword1, keyword2, keyword3',
			article_id: content.article_id,
			action: actionToEditorAction[action],
			timestamp: new Date().toISOString()
		},
		conversation_id: 'test-conv-id'
	};
}

/**
 * Build a general chat response (no action)
 */
export function buildChatResponse(message: string): MockChatResponse {
	return {
		response: message,
		conversation_id: 'test-conv-id'
	};
}

/**
 * Build an error response
 */
export function buildErrorResponse(error: string): MockChatResponse {
	return {
		response: error,
		conversation_id: 'test-conv-id'
	};
}

// =============================================================================
// Predefined Mock Responses
// =============================================================================

/**
 * Standard navigation responses keyed by trigger phrase
 */
export const NAVIGATION_RESPONSES: Record<string, MockChatResponse> = {
	// Home navigation
	'go home': buildNavigationResponse('home'),
	'take me home': buildNavigationResponse('home'),
	'go to home': buildNavigationResponse('home'),
	'go to the main page': buildNavigationResponse('home'),

	// Search navigation
	'go to search': buildNavigationResponse('reader_search'),
	'open search': buildNavigationResponse('reader_search'),
	'search articles': buildNavigationResponse('reader_search'),

	// Profile navigation
	'go to my profile': buildNavigationResponse('user_profile'),
	'show my profile': buildNavigationResponse('user_profile'),
	'open profile': buildNavigationResponse('user_profile'),

	// Settings navigation
	'go to settings': buildNavigationResponse('user_settings'),
	'open settings': buildNavigationResponse('user_settings'),
	'show settings': buildNavigationResponse('user_settings'),

	// Analyst navigation
	'go to analyst': buildNavigationResponse('analyst_dashboard', 'macro'),
	'open analyst dashboard': buildNavigationResponse('analyst_dashboard', 'macro'),
	'go to my articles': buildNavigationResponse('analyst_dashboard', 'macro'),

	// Editor navigation
	'go to editor': buildNavigationResponse('editor_dashboard', 'macro'),
	'open editor dashboard': buildNavigationResponse('editor_dashboard', 'macro'),
	'show review queue': buildNavigationResponse('editor_dashboard', 'macro'),

	// Admin navigation
	'go to admin': buildNavigationResponse('admin_articles', 'macro'),
	'open admin panel': buildNavigationResponse('admin_articles', 'macro'),
	'manage articles': buildNavigationResponse('admin_articles', 'macro'),

	// Root admin navigation
	'go to user management': buildNavigationResponse('root_users'),
	'manage users': buildNavigationResponse('root_users'),
	'go to global admin': buildNavigationResponse('root_users'),
	'open topic management': buildNavigationResponse('root_topics'),
	'manage topics': buildNavigationResponse('root_topics'),

	// Topic-specific navigation
	'show me macro articles': buildNavigationResponse('reader_topic', 'macro'),
	'go to equity topic': buildNavigationResponse('reader_topic', 'equity'),
	'show credit articles': buildNavigationResponse('reader_topic', 'credit')
};

/**
 * Content editing responses keyed by trigger phrase
 */
export const CONTENT_RESPONSES: Record<string, MockChatResponse> = {
	// Headline regeneration
	'give me a better headline': buildContentResponse('regenerate_headline', {
		headline: 'A More Compelling Headline for Your Article'
	}),
	'suggest a new headline': buildContentResponse('regenerate_headline', {
		headline: 'Fresh Perspective: Market Analysis Deep Dive'
	}),
	'rephrase the headline': buildContentResponse('regenerate_headline', {
		headline: 'Rephrased: Understanding Market Dynamics'
	}),

	// Keywords regeneration
	'suggest keywords': buildContentResponse('regenerate_keywords', {
		keywords: 'market analysis, investment strategy, economic trends, portfolio management'
	}),
	'generate new keywords': buildContentResponse('regenerate_keywords', {
		keywords: 'macroeconomics, inflation, interest rates, monetary policy'
	}),
	'better keywords please': buildContentResponse('regenerate_keywords', {
		keywords: 'equity markets, stock analysis, sector rotation, market outlook'
	}),

	// Section editing
	'rewrite the introduction': buildContentResponse('edit_section', {
		content: '## Introduction\n\nThis is a rewritten introduction that provides a compelling overview of the article topic. It sets the stage for the detailed analysis that follows.\n\n## Analysis\n\nExisting analysis content remains unchanged.'
	}),
	'expand the analysis section': buildContentResponse('edit_section', {
		content: '## Introduction\n\nExisting introduction.\n\n## Analysis\n\nThis is an expanded analysis section with more detailed insights, additional data points, and deeper market commentary. The expanded analysis provides comprehensive coverage of all relevant factors.'
	}),
	'shorten the conclusion': buildContentResponse('edit_section', {
		content: '## Conclusion\n\nIn summary, the key takeaways are clear market direction and strategic recommendations.'
	}),

	// Content refinement
	'make it more concise': buildContentResponse('refine_content', {
		content: 'A more concise version of the article that removes redundancy and focuses on key points.'
	}),
	'make it more professional': buildContentResponse('refine_content', {
		content: 'A professionally refined version of the article with formal tone and industry-standard terminology.'
	}),
	'add more detail': buildContentResponse('refine_content', {
		content: 'An expanded version of the article with additional details, examples, and supporting data.'
	}),
	'simplify the language': buildContentResponse('refine_content', {
		content: 'A simplified version of the article using clearer, more accessible language for a broader audience.'
	}),

	// Full content regeneration
	'rewrite the entire article': buildContentResponse('regenerate_content', {
		headline: 'Completely Rewritten Article',
		content: 'This is a completely rewritten article with fresh content, new structure, and updated analysis.',
		keywords: 'new, rewritten, fresh analysis'
	}),
	'start over': buildContentResponse('regenerate_content', {
		headline: 'Fresh Start: New Article Content',
		content: 'Starting fresh with completely new content based on the original topic.',
		keywords: 'fresh start, new content'
	}),

	// New article creation
	'write an article about inflation': buildContentResponse('create', {
		headline: 'Understanding Inflation: Causes, Effects, and Investment Strategies',
		content: '## Introduction\n\nInflation remains a key concern for investors and policymakers alike.\n\n## Analysis\n\nCurrent inflation trends show...\n\n## Conclusion\n\nInvestors should consider...',
		keywords: 'inflation, monetary policy, investment strategy, economic analysis',
		article_id: 123
	}),
	'create a new article': buildContentResponse('create', {
		headline: 'New Article Draft',
		content: '## Introduction\n\nYour new article content starts here.\n\n## Main Content\n\nAdd your analysis and insights.\n\n## Conclusion\n\nSummarize your key points.',
		keywords: 'draft, new article',
		article_id: 124
	})
};

// =============================================================================
// Page Helpers
// =============================================================================

/**
 * Mock the chat API endpoint with custom response logic
 */
export async function mockChatAPI(
	page: Page,
	responseMap?: Record<string, MockChatResponse>
): Promise<void> {
	const responses = { ...NAVIGATION_RESPONSES, ...CONTENT_RESPONSES, ...responseMap };

	await page.route('**/api/chat**', async (route: Route) => {
		const request = route.request();

		// Handle GET requests (conversation history)
		if (request.method() === 'GET') {
			await route.fulfill({
				status: 200,
				contentType: 'application/json',
				body: JSON.stringify({ messages: [] })
			});
			return;
		}

		// Handle POST requests (new messages)
		if (request.method() === 'POST') {
			const body = await request.postDataJSON();
			const userMessage = body.message?.toLowerCase() || '';

			// Find matching response
			let response: MockChatResponse | undefined;
			for (const [trigger, resp] of Object.entries(responses)) {
				if (userMessage.includes(trigger.toLowerCase())) {
					response = resp;
					break;
				}
			}

			// Default response if no match
			if (!response) {
				response = buildChatResponse(
					`I received your message: "${body.message}". How can I help you further?`
				);
			}

			await route.fulfill({
				status: 200,
				contentType: 'application/json',
				body: JSON.stringify(response)
			});
			return;
		}

		// Pass through other methods
		await route.continue();
	});
}

/**
 * Mock chat API with specific responses for a test scenario
 */
export async function mockChatWithResponses(
	page: Page,
	responses: Array<{ trigger: string; response: MockChatResponse }>
): Promise<void> {
	const responseMap: Record<string, MockChatResponse> = {};
	for (const { trigger, response } of responses) {
		responseMap[trigger.toLowerCase()] = response;
	}
	await mockChatAPI(page, responseMap);
}

/**
 * Send a chat message and wait for response
 */
export async function sendChatMessage(page: Page, message: string): Promise<void> {
	// Wait for input to be enabled before interacting
	await page.waitForSelector('[data-testid="chat-input"]:not([disabled])', { state: 'visible', timeout: 5000 });

	await page.fill('[data-testid="chat-input"]', message);
	await page.press('[data-testid="chat-input"]', 'Enter');

	// Wait for assistant response to appear
	// Mocked responses are instant, but give some time for UI to update
	await page.waitForSelector('[data-testid="chat-message-assistant"]', { timeout: 5000 });
}

/**
 * Get the last assistant message text
 */
export async function getLastAssistantMessage(page: Page): Promise<string> {
	const messages = page.locator('[data-testid="chat-message-assistant"]');
	const count = await messages.count();
	if (count === 0) return '';
	return await messages.nth(count - 1).textContent() || '';
}

/**
 * Check if a UI action was dispatched
 */
export async function wasUIActionDispatched(page: Page, actionType: string): Promise<boolean> {
	return await page.evaluate((type) => {
		const store = (window as any).__actionStore;
		if (!store) return false;
		const lastAction = store.getLastDispatchedAction?.();
		return lastAction?.type === type;
	}, actionType);
}

/**
 * Get the last dispatched UI action
 */
export async function getLastDispatchedAction(
	page: Page
): Promise<MockUIAction | null> {
	return await page.evaluate(() => {
		const store = (window as any).__actionStore;
		if (!store) return null;
		return store.getLastDispatchedAction?.() || null;
	});
}

/**
 * Wait for navigation to complete after chat command
 */
export async function waitForChatNavigation(page: Page, expectedUrl: string | RegExp): Promise<void> {
	// Navigation after chat command should be quick since we're using mocked responses
	await page.waitForURL(expectedUrl, { timeout: 5000 });
}

/**
 * Check if editor content was updated
 */
export async function getEditorContent(page: Page): Promise<MockEditorContent | null> {
	return await page.evaluate(() => {
		// Check for editor content in window or store
		const editorStore = (window as any).__editorStore;
		if (editorStore?.getContent) {
			return editorStore.getContent();
		}
		return null;
	});
}

/**
 * Verify chat panel is visible and ready for interaction
 */
export async function ensureChatPanelReady(page: Page): Promise<void> {
	// Wait for chat panel to be visible
	await page.waitForSelector('[data-testid="chat-panel"]', { state: 'visible', timeout: 10000 });

	// Wait for chat input to be visible AND enabled (not disabled)
	// The input is disabled until auth is fully loaded
	await page.waitForSelector('[data-testid="chat-input"]:not([disabled])', { state: 'visible', timeout: 10000 });
}
