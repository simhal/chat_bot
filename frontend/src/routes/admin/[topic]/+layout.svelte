<script lang="ts">
	import { page } from '$app/stores';
	import { auth } from '$lib/stores/auth';
	import { goto } from '$app/navigation';
	import { onMount, onDestroy } from 'svelte';
	import { navigationContext, type SectionName } from '$lib/stores/navigation';
	import { actionStore, type UIAction, type ActionResult } from '$lib/stores/actions';
	import { getEntitledTopics, type Topic } from '$lib/api';

	let { children } = $props();

	// Get topic from URL params
	let topic = $derived($page.params.topic);

	// Determine current section from URL path (matching sections.json)
	let currentSection = $derived.by(() => {
		const path = $page.url.pathname;
		if (path.includes('/resources')) return 'admin_resources';
		if (path.includes('/prompts')) return 'admin_prompts';
		return 'admin_articles';
	});

	// For nav tab highlighting
	let currentView = $derived.by(() => {
		const path = $page.url.pathname;
		if (path.includes('/resources')) return 'resources';
		if (path.includes('/prompts')) return 'prompts';
		return 'articles';
	});

	// Topics the user has admin access to
	let adminTopics: Topic[] = $state([]);
	let topicsLoading = $state(true);

	// Check permissions
	let isGlobalAdmin = $derived($auth.user?.scopes?.includes('global:admin') || false);
	let hasAdminAccess = $derived(
		isGlobalAdmin || adminTopics.some((t) => t.slug === topic)
	);

	// Update navigation context when section changes
	$effect(() => {
		if ($auth.isAuthenticated && hasAdminAccess) {
			navigationContext.setSection(currentSection as SectionName);
			navigationContext.setTopic(topic);
		}
	});

	// Redirect if no admin access for this topic
	$effect(() => {
		if ($auth.isAuthenticated && !topicsLoading && !hasAdminAccess) {
			goto('/');
		}
	});

	async function loadTopics() {
		try {
			topicsLoading = true;
			adminTopics = await getEntitledTopics('admin');
		} catch (e) {
			console.error('Failed to load topics:', e);
			adminTopics = [];
		} finally {
			topicsLoading = false;
		}
	}

	// Action handlers
	let actionUnsubscribers: (() => void)[] = [];

	async function handleSelectTopicAction(action: UIAction): Promise<ActionResult> {
		const newTopic = action.params?.topic;
		if (!newTopic) {
			return { success: false, action: 'select_topic', error: 'No topic specified' };
		}
		goto(`/admin/${newTopic}/articles`);
		return { success: true, action: 'select_topic', message: `Switched to ${newTopic}` };
	}

	onMount(() => {
		loadTopics();
		actionUnsubscribers.push(
			actionStore.registerHandler('select_topic', handleSelectTopicAction)
		);
	});

	onDestroy(() => {
		actionUnsubscribers.forEach((unsub) => unsub());
	});

	// Format topic for display
	let topicDisplay = $derived(topic?.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()));
</script>

<div class="admin-container">
	<div class="admin-header">
		<div class="header-left">
			<h1>Topic Administration: {topicDisplay}</h1>
			{#if adminTopics.length > 1}
				<select
					class="topic-select"
					value={topic}
					onchange={(e) => goto(`/admin/${e.currentTarget.value}/articles`)}
				>
					{#each adminTopics as t}
						<option value={t.slug}>{t.title}</option>
					{/each}
				</select>
			{/if}
		</div>
		<nav class="admin-actions">
			<a
				href="/admin/{topic}/articles"
				class="action-btn"
				class:active={currentView === 'articles'}
			>
				Articles
			</a>
			<a
				href="/admin/{topic}/resources"
				class="action-btn"
				class:active={currentView === 'resources'}
			>
				Resources
			</a>
			<a
				href="/admin/{topic}/prompts"
				class="action-btn"
				class:active={currentView === 'prompts'}
			>
				Prompts
			</a>
		</nav>
	</div>

	{#if topicsLoading}
		<div class="loading">Loading...</div>
	{:else}
		{@render children()}
	{/if}
</div>

<style>
	:global(body) {
		background: #fafafa;
	}

	.admin-container {
		max-width: 1600px;
		margin: 0 auto;
		background: white;
		min-height: 100vh;
	}

	.admin-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 1rem 1.5rem;
		background: white;
		border-bottom: 1px solid #e5e7eb;
		margin-bottom: 2rem;
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: 1rem;
	}

	.header-left h1 {
		margin: 0;
		font-size: 1.25rem;
		font-weight: 600;
		color: #1f2937;
	}

	.topic-select {
		padding: 0.5rem;
		border: 1px solid #e5e7eb;
		border-radius: 6px;
		background: white;
		font-size: 0.875rem;
	}

	.admin-actions {
		display: flex;
		gap: 0.5rem;
	}

	.action-btn {
		padding: 0.5rem 1rem;
		background: #f3f4f6;
		color: #374151;
		border: 1px solid #e5e7eb;
		border-radius: 6px;
		font-size: 0.875rem;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.15s ease;
		text-decoration: none;
	}

	.action-btn:hover {
		background: #e5e7eb;
		border-color: #d1d5db;
	}

	.action-btn.active {
		background: #6366f1;
		color: white;
		border-color: #6366f1;
	}

	.loading {
		text-align: center;
		padding: 3rem;
		color: #6b7280;
	}
</style>
