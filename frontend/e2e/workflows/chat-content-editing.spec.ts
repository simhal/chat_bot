import { test, expect, type Page } from '@playwright/test';
import { loginAsAnalyst, loginAsEditor } from '../fixtures/auth';
import {
	mockChatAPI,
	sendChatMessage,
	getLastAssistantMessage,
	ensureChatPanelReady,
	buildContentResponse,
	mockChatWithResponses,
	MockEditorContent
} from '../fixtures/chat';

/**
 * Chat Content Editing E2E Tests
 *
 * Tests that verify analysts can edit article content using natural language
 * chat commands while in the article editor (analyst_editor section).
 *
 * The v2 agent build provides smooth content editing with these capabilities:
 * - Regenerate just the headline
 * - Regenerate just the keywords
 * - Edit specific sections (introduction, conclusion, etc.)
 * - Refine content style/tone (more concise, professional, etc.)
 * - Full content regeneration
 * - New article creation
 */

// =============================================================================
// Test Helpers
// =============================================================================

/**
 * Mock article data in the editor
 */
async function mockArticleInEditor(page: Page, article: MockEditorContent): Promise<void> {
	// Set topic in localStorage (required by editor page)
	await page.evaluate(() => {
		localStorage.setItem('selected_topic', 'macro');
	});
	// Mock the analyst article API endpoint
	await page.route('**/api/analyst/*/article/*', async (route) => {
		if (route.request().method() === 'GET') {
			await route.fulfill({
				status: 200,
				contentType: 'application/json',
				body: JSON.stringify({
					id: article.article_id || 123,
					headline: article.headline || 'Test Article Headline',
					content: article.content || 'Test article content.',
					keywords: article.keywords || 'test, keywords',
					topic: 'macro',
					status: 'draft',
					created_at: new Date().toISOString(),
					updated_at: new Date().toISOString()
				})
			});
		} else {
			await route.continue();
		}
	});
	// Mock resources API (required for editor to finish loading)
	await page.route('**/api/resources/**', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify({ resources: [] })
		});
	});
}

/**
 * Check if editor content was updated with expected values
 */
async function expectEditorContentUpdated(
	page: Page,
	expectedContent: Partial<MockEditorContent>
): Promise<void> {
	// Wait for editor to update
	await page.waitForTimeout(500);

	// Check headline if expected
	if (expectedContent.headline) {
		const headlineInput = page.locator('[data-testid="article-headline-input"], [data-testid="editor-headline"]');
		if (await headlineInput.isVisible()) {
			await expect(headlineInput).toHaveValue(expectedContent.headline);
		}
	}

	// Check keywords if expected
	if (expectedContent.keywords) {
		const keywordsInput = page.locator('[data-testid="article-keywords-input"], [data-testid="editor-keywords"]');
		if (await keywordsInput.isVisible()) {
			await expect(keywordsInput).toHaveValue(expectedContent.keywords);
		}
	}
}

// =============================================================================
// Headline Regeneration Tests
// =============================================================================

test.describe('Chat Content Editing - Headline Regeneration', () => {
	test.beforeEach(async ({ page }) => {
		await loginAsAnalyst(page);
		await mockArticleInEditor(page, {
			article_id: 123,
			headline: 'Original Headline',
			content: 'Original content.',
			keywords: 'original, keywords'
		});
		await mockChatAPI(page);
	});

	test('should regenerate headline with "better headline" command', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'give me a better headline');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('headline');
	});

	test('should regenerate headline with "new headline" command', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await mockChatWithResponses(page, [
			{
				trigger: 'suggest a new headline',
				response: buildContentResponse('regenerate_headline', {
					headline: 'Freshly Generated Headline for Analysis'
				})
			}
		]);

		await sendChatMessage(page, 'suggest a new headline');

		const response = await getLastAssistantMessage(page);
		expect(response).toContain('Freshly Generated Headline');
	});

	test('should regenerate headline with "rephrase" command', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'rephrase the headline');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('headline');
	});

	test('should show new headline in response', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await mockChatWithResponses(page, [
			{
				trigger: 'catchier headline',
				response: buildContentResponse('regenerate_headline', {
					headline: 'Market Dynamics: A Deep Dive into Economic Trends'
				})
			}
		]);

		await sendChatMessage(page, 'give me a catchier headline');

		const response = await getLastAssistantMessage(page);
		expect(response).toContain('Market Dynamics');
	});
});

// =============================================================================
// Keywords Regeneration Tests
// =============================================================================

test.describe('Chat Content Editing - Keywords Regeneration', () => {
	test.beforeEach(async ({ page }) => {
		await loginAsAnalyst(page);
		await mockArticleInEditor(page, {
			article_id: 123,
			headline: 'Test Article',
			content: 'Test content about market analysis.',
			keywords: 'test, keywords'
		});
		await mockChatAPI(page);
	});

	test('should regenerate keywords with "suggest keywords" command', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'suggest keywords');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('keyword');
	});

	test('should regenerate keywords with "new keywords" command', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'generate new keywords');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('keyword');
	});

	test('should regenerate keywords with "better keywords" command', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'better keywords please');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('keyword');
	});

	test('should show new keywords in response', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await mockChatWithResponses(page, [
			{
				trigger: 'seo keywords',
				response: buildContentResponse('regenerate_keywords', {
					keywords: 'market analysis, investment strategy, portfolio management, risk assessment'
				})
			}
		]);

		await sendChatMessage(page, 'give me seo keywords');

		const response = await getLastAssistantMessage(page);
		expect(response).toContain('market analysis');
	});
});

// =============================================================================
// Section Editing Tests
// =============================================================================

test.describe('Chat Content Editing - Section Editing', () => {
	test.beforeEach(async ({ page }) => {
		await loginAsAnalyst(page);
		await mockArticleInEditor(page, {
			article_id: 123,
			headline: 'Test Article',
			content: '## Introduction\n\nOld intro.\n\n## Analysis\n\nDetailed analysis.\n\n## Conclusion\n\nOld conclusion.',
			keywords: 'test, keywords'
		});
		await mockChatAPI(page);
	});

	test('should edit introduction section', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'rewrite the introduction');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toMatch(/edit|rewrit|introduction/);
	});

	test('should expand analysis section', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'expand the analysis section');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toMatch(/edit|expand|analysis/);
	});

	test('should shorten conclusion section', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'shorten the conclusion');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toMatch(/edit|short|conclusion/);
	});

	test('should improve specific paragraph', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await mockChatWithResponses(page, [
			{
				trigger: 'improve the opening paragraph',
				response: buildContentResponse('edit_section', {
					content: '## Introduction\n\nA compelling opening that draws readers in.\n\n## Analysis\n\nExisting analysis.\n\n## Conclusion\n\nExisting conclusion.'
				}, 'I\'ve improved the opening paragraph with a more compelling hook.')
			}
		]);

		await sendChatMessage(page, 'improve the opening paragraph');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('opening');
	});

	test('should add more detail to section', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await mockChatWithResponses(page, [
			{
				trigger: 'add more detail to the methodology section',
				response: buildContentResponse('edit_section', {
					content: '## Methodology\n\nExpanded methodology with detailed explanation of data sources, analytical techniques, and validation procedures.'
				}, 'I\'ve added more detail to the methodology section.')
			}
		]);

		await sendChatMessage(page, 'add more detail to the methodology section');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('methodology');
	});
});

// =============================================================================
// Content Refinement Tests
// =============================================================================

test.describe('Chat Content Editing - Content Refinement', () => {
	test.beforeEach(async ({ page }) => {
		await loginAsAnalyst(page);
		await mockArticleInEditor(page, {
			article_id: 123,
			headline: 'Test Article',
			content: 'This is test content that needs refinement.',
			keywords: 'test, keywords'
		});
		await mockChatAPI(page);
	});

	test('should make content more concise', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'make it more concise');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toMatch(/concise|applied|refine/);
	});

	test('should make content more professional', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'make it more professional');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toMatch(/professional|applied|refine/);
	});

	test('should add more detail to content', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'add more detail');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toMatch(/detail|applied|refine/);
	});

	test('should simplify language', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'simplify the language');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toMatch(/simplif|applied|refine/);
	});

	test('should adjust tone', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await mockChatWithResponses(page, [
			{
				trigger: 'make the tone more formal',
				response: buildContentResponse('refine_content', {
					content: 'A more formally written version of the article with appropriate business language.'
				}, 'I\'ve adjusted the tone to be more formal.')
			}
		]);

		await sendChatMessage(page, 'make the tone more formal');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('formal');
	});

	test('should polish content', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await mockChatWithResponses(page, [
			{
				trigger: 'polish the article',
				response: buildContentResponse('refine_content', {
					content: 'A polished and refined version of the article.'
				}, 'I\'ve polished the article for better readability.')
			}
		]);

		await sendChatMessage(page, 'polish the article');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('polish');
	});
});

// =============================================================================
// Full Content Regeneration Tests
// =============================================================================

test.describe('Chat Content Editing - Full Regeneration', () => {
	test.beforeEach(async ({ page }) => {
		await loginAsAnalyst(page);
		await mockArticleInEditor(page, {
			article_id: 123,
			headline: 'Original Article',
			content: 'Original content that will be completely rewritten.',
			keywords: 'original, keywords'
		});
		await mockChatAPI(page);
	});

	test('should regenerate entire article', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'rewrite the entire article');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toMatch(/rewrite|rewrit|content/);
	});

	test('should start over with fresh content', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'start over');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toMatch(/start|fresh|content|rewrite/);
	});

	test('should regenerate content with new direction', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await mockChatWithResponses(page, [
			{
				trigger: 'rewrite with a bullish perspective',
				response: buildContentResponse('regenerate_content', {
					headline: 'Market Outlook: Bullish Indicators Point to Growth',
					content: 'A completely rewritten article with a bullish perspective on market conditions.',
					keywords: 'bullish, growth, market outlook'
				}, 'I\'ve rewritten the article with a bullish perspective.')
			}
		]);

		await sendChatMessage(page, 'rewrite with a bullish perspective');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('bullish');
	});
});

// =============================================================================
// New Article Creation Tests
// =============================================================================

test.describe('Chat Content Editing - New Article Creation', () => {
	test.beforeEach(async ({ page }) => {
		await loginAsAnalyst(page);
		await mockChatAPI(page);
	});

	test('should create new article about specific topic', async ({ page }) => {
		await page.goto('/analyst/macro');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'write an article about inflation');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toMatch(/draft|article|inflation/);
	});

	test('should create new article with generic command', async ({ page }) => {
		await page.goto('/analyst/macro');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'create a new article');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toMatch(/draft|article|new/);
	});

	test('should generate article with specific focus', async ({ page }) => {
		await page.goto('/analyst/macro');
		await ensureChatPanelReady(page);

		await mockChatWithResponses(page, [
			{
				trigger: 'write an analysis of Q4 earnings',
				response: buildContentResponse('create', {
					headline: 'Q4 Earnings Analysis: Key Takeaways and Market Impact',
					content: '## Introduction\n\nQ4 earnings season has delivered...\n\n## Analysis\n\nKey findings include...\n\n## Conclusion\n\nLooking ahead...',
					keywords: 'Q4 earnings, market analysis, corporate performance',
					article_id: 456
				}, 'I\'ve drafted an analysis of Q4 earnings.')
			}
		]);

		await sendChatMessage(page, 'write an analysis of Q4 earnings');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('q4');
	});
});

// =============================================================================
// Editor Context Detection Tests
// =============================================================================

test.describe('Chat Content Editing - Context Detection', () => {
	test.beforeEach(async ({ page }) => {
		await loginAsAnalyst(page);
		await mockArticleInEditor(page, {
			article_id: 123,
			headline: 'Test Article',
			content: 'Test content.',
			keywords: 'test'
		});
	});

	test('should detect headline request in editor context', async ({ page }) => {
		await mockChatWithResponses(page, [
			{
				trigger: 'this headline is boring',
				response: buildContentResponse('regenerate_headline', {
					headline: 'Exciting New Headline That Captures Attention'
				}, 'I\'ve generated a more engaging headline for you.')
			}
		]);

		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'this headline is boring');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('headline');
	});

	test('should detect content refinement request', async ({ page }) => {
		await mockChatWithResponses(page, [
			{
				trigger: 'it is too wordy',
				response: buildContentResponse('refine_content', {
					content: 'A more concise version of the content.'
				}, 'I\'ve made the content more concise.')
			}
		]);

		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'it is too wordy');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toMatch(/concise|word/);
	});

	test('should detect section edit request', async ({ page }) => {
		await mockChatWithResponses(page, [
			{
				trigger: 'the intro needs work',
				response: buildContentResponse('edit_section', {
					content: '## Introduction\n\nA reworked introduction.\n\n## Rest\n\nRest of article.'
				}, 'I\'ve reworked the introduction.')
			}
		]);

		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'the intro needs work');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toMatch(/intro|rework/);
	});
});

// =============================================================================
// Combined Workflow Tests
// =============================================================================

test.describe('Chat Content Editing - Combined Workflows', () => {
	test.beforeEach(async ({ page }) => {
		await loginAsAnalyst(page);
		await mockArticleInEditor(page, {
			article_id: 123,
			headline: 'Original Headline',
			content: '## Introduction\n\nIntro content.\n\n## Analysis\n\nAnalysis content.',
			keywords: 'original, keywords'
		});
		await mockChatAPI(page);
	});

	test('should support multiple edits in sequence', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		// First: regenerate headline
		await sendChatMessage(page, 'give me a better headline');
		let response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('headline');

		// Second: regenerate keywords
		await sendChatMessage(page, 'suggest keywords');
		response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('keyword');

		// Third: refine content
		await sendChatMessage(page, 'make it more concise');
		response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toMatch(/concise|applied/);
	});

	test('should allow navigation then return to editing', async ({ page }) => {
		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		// Edit content
		await sendChatMessage(page, 'give me a better headline');
		let response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('headline');

		// Navigate away
		await mockChatWithResponses(page, [
			{
				trigger: 'go to search',
				response: {
					response_text: 'Opening search.',
					ui_action: { type: 'goto', params: { section: 'reader_search' } },
					conversation_id: 'test'
				}
			}
		]);

		await sendChatMessage(page, 'go to search');
		await page.waitForURL('/reader/search', { timeout: 5000 });

		// Navigate back
		await mockChatWithResponses(page, [
			{
				trigger: 'go back to my article',
				response: {
					response_text: 'Opening article editor.',
					ui_action: { type: 'goto', params: { section: 'analyst_editor', article_id: 123 } },
					conversation_id: 'test'
				}
			}
		]);

		await sendChatMessage(page, 'go back to my article');
		await page.waitForURL(/\/analyst\/edit\//, { timeout: 5000 });
	});
});

// =============================================================================
// Error Handling Tests
// =============================================================================

test.describe('Chat Content Editing - Error Handling', () => {
	test.beforeEach(async ({ page }) => {
		await loginAsAnalyst(page);
	});

	test('should handle missing article gracefully', async ({ page }) => {
		await mockChatWithResponses(page, [
			{
				trigger: 'better headline',
				response: {
					response_text: 'Please open an article in the editor first.',
					conversation_id: 'test'
				}
			}
		]);

		// Go to analyst dashboard (not editor)
		await page.goto('/analyst/macro');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'give me a better headline');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toMatch(/open|article|editor|first/);
	});

	test('should handle content generation failure', async ({ page }) => {
		await mockArticleInEditor(page, { article_id: 123 });
		await mockChatWithResponses(page, [
			{
				trigger: 'rewrite everything',
				response: {
					response_text: 'Content generation failed: Unable to process request. Please try again.',
					conversation_id: 'test'
				}
			}
		]);

		await page.goto('/analyst/edit/123');
		await ensureChatPanelReady(page);

		await sendChatMessage(page, 'rewrite everything');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toMatch(/fail|error|unable|try again/);
	});
});

// =============================================================================
// Permission Tests
// =============================================================================

test.describe('Chat Content Editing - Permissions', () => {
	test('editor should be able to suggest changes to articles', async ({ page }) => {
		await loginAsEditor(page);
		await mockChatAPI(page);

		await page.goto('/editor/macro');
		await ensureChatPanelReady(page);

		await mockChatWithResponses(page, [
			{
				trigger: 'suggest improvements for article 123',
				response: {
					response_text: 'Here are my suggestions for improving article #123:\n\n1. The headline could be more engaging\n2. Consider adding more data points\n3. The conclusion could be stronger',
					conversation_id: 'test'
				}
			}
		]);

		await sendChatMessage(page, 'suggest improvements for article 123');

		const response = await getLastAssistantMessage(page);
		expect(response.toLowerCase()).toContain('suggestion');
	});
});
