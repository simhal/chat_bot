<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto, beforeNavigate, afterNavigate } from '$app/navigation';
	import favicon from '$lib/assets/favicon.svg';
	import Header from '$lib/components/Header.svelte';
	import SplitPane from '$lib/components/SplitPane.svelte';
	import ChatPanel from '$lib/components/ChatPanel.svelte';
	import { actionStore } from '$lib/stores/actions';
	import { buildSectionUrl, type SectionName } from '$lib/stores/navigation';

	let { children } = $props();

	// Navigation history for go back functionality
	let navigationHistory: string[] = [];
	const MAX_HISTORY = 50;

	beforeNavigate(({ from }) => {
		if (from?.url) {
			navigationHistory.push(from.url.pathname);
			if (navigationHistory.length > MAX_HISTORY) {
				navigationHistory.shift();
			}
		}
	});

	// Store unsubscribe functions for cleanup
	let unsubscribers: (() => void)[] = [];

	onMount(() => {
		// =============================================================================
		// Global Navigation Handler - Unified 'goto' action
		// =============================================================================
		// Handles all navigation via the unified 'goto' action with section parameter.
		// Section names come from shared/sections.json
		unsubscribers.push(
			actionStore.registerHandler('goto', async (action) => {
				const section = action.params?.section as SectionName;
				const topic = action.params?.topic;
				const articleId = action.params?.article_id;

				console.log('🧭 goto handler:', { section, topic, articleId });

				if (!section) {
					return { success: false, action: 'goto', error: 'No section specified' };
				}

				// Build URL from section and parameters
				const url = buildSectionUrl(section, topic, articleId);
				console.log('🔗 Navigating to:', url);

				await goto(url, { invalidateAll: true });
				return { success: true, action: 'goto', message: `Navigated to ${section}` };
			})
		);

		// =============================================================================
		// Go Back Navigation Handler
		// =============================================================================
		// Uses browser history to go back
		const gotoBackHandler = actionStore.registerHandler('goto_back', async () => {
			// Check if we have tracked navigation history
			if (navigationHistory.length > 0) {
				const previousPath = navigationHistory.pop();
				await goto(previousPath!, { invalidateAll: true });
				return { success: true, action: 'goto_back', message: 'Navigated to previous page' };
			} else if (typeof window !== 'undefined' && window.history.length > 1) {
				// Use browser history if available
				window.history.back();
				return { success: true, action: 'goto_back', message: 'Navigated back via browser history' };
			} else {
				// No history, go to home
				await goto('/', { invalidateAll: true });
				return { success: true, action: 'goto_back', message: 'No history, navigated to home' };
			}
		});
		unsubscribers.push(gotoBackHandler);

		// =============================================================================
		// Global Actions - select_topic, select_article, logout
		// =============================================================================
		unsubscribers.push(
			actionStore.registerHandler('select_topic', async (action) => {
				const topic = action.params?.topic;
				console.log('📁 select_topic handler:', topic);

				if (!topic) {
					return { success: false, action: 'select_topic', error: 'No topic specified' };
				}

				// Navigate to reader_topic with the selected topic
				const url = buildSectionUrl('reader_topic', topic);
				await goto(url, { invalidateAll: true });
				return { success: true, action: 'select_topic', message: `Selected topic: ${topic}` };
			})
		);

		unsubscribers.push(
			actionStore.registerHandler('select_article', async (action) => {
				const articleId = action.params?.article_id;
				console.log('📄 select_article handler:', articleId);

				if (!articleId) {
					return { success: false, action: 'select_article', error: 'No article_id specified' };
				}

				// This action updates context - actual navigation depends on current page
				// The page component should handle the article selection
				return { success: true, action: 'select_article', data: { article_id: articleId } };
			})
		);

		unsubscribers.push(
			actionStore.registerHandler('logout', async () => {
				console.log('🚪 logout handler');
				// Clear auth and redirect to login
				window.location.href = '/auth/logout';
				return { success: true, action: 'logout' };
			})
		);
	});

	onDestroy(() => {
		// Clean up all registered handlers
		unsubscribers.forEach((unsub) => unsub());
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<Header />

<SplitPane initialRatio={0.7} minUpperPx={200} minLowerPx={150}>
	{#snippet upperContent()}
		<div class="upper-content">
			{@render children()}
		</div>
	{/snippet}
	{#snippet lowerContent()}
		<ChatPanel />
	{/snippet}
</SplitPane>

<style>
	.upper-content {
		height: 100%;
		overflow: auto;
	}
</style>
