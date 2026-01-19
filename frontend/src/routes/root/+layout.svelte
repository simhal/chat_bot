<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { getAdminUsers, getAdminGroups, getPromptModules, getTonalities, getGlobalResources, getTopics, recalculateAllTopicStats, type PromptModule, type TonalityOption, type Resource, type Topic } from '$lib/api';
	import { onMount, onDestroy, setContext } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { navigationContext } from '$lib/stores/navigation';
	import { actionStore, type UIAction, type ActionResult } from '$lib/stores/actions';
	import { writable, type Writable } from 'svelte/store';

	let { children } = $props();

	// Shared state stores (passed to children via context)
	const users: Writable<any[]> = writable([]);
	const groups: Writable<any[]> = writable([]);
	const prompts: Writable<PromptModule[]> = writable([]);
	const availableTonalities: Writable<TonalityOption[]> = writable([]);
	const resources: Writable<Resource[]> = writable([]);
	const dbTopics: Writable<Topic[]> = writable([]);
	const allTopics: Writable<Array<{ id: string; label: string }>> = writable([]);
	const loading: Writable<boolean> = writable(true);
	const error: Writable<string> = writable('');

	// Set context for child components
	setContext('rootAdminUsers', users);
	setContext('rootAdminGroups', groups);
	setContext('rootAdminPrompts', prompts);
	setContext('rootAdminTonalities', availableTonalities);
	setContext('rootAdminResources', resources);
	setContext('rootAdminDbTopics', dbTopics);
	setContext('rootAdminAllTopics', allTopics);
	setContext('rootAdminLoading', loading);
	setContext('rootAdminError', error);

	// Loading states for specific views
	let topicsLoading = $state(true);
	let resourcesLoading = $state(false);
	let promptsLoading = $state(false);

	// Check permissions - require global:admin
	let isGlobalAdmin = $derived($auth.user?.scopes?.includes('global:admin') || false);

	// Redirect if no global admin access
	$effect(() => {
		if ($auth.isAuthenticated && !isGlobalAdmin) {
			goto('/');
		}
	});

	// Determine current section from URL path (matching sections.json)
	let currentSection = $derived.by(() => {
		const path = $page.url.pathname;
		if (path.includes('/root/groups')) return 'root_groups';
		if (path.includes('/root/prompts')) return 'root_prompts';
		if (path.includes('/root/resources')) return 'root_resources';
		if (path.includes('/root/topics')) return 'root_topics';
		if (path.includes('/root/tonalities')) return 'root_tonalities';
		return 'root_users';
	});

	// For nav tab highlighting
	let currentView = $derived.by(() => {
		const path = $page.url.pathname;
		if (path.includes('/root/groups')) return 'groups';
		if (path.includes('/root/prompts')) return 'prompts';
		if (path.includes('/root/resources')) return 'resources';
		if (path.includes('/root/topics')) return 'topics';
		if (path.includes('/root/tonalities')) return 'tonalities';
		return 'users';
	});

	// Update navigation context when section changes (using sections.json section names)
	$effect(() => {
		if ($auth.isAuthenticated && isGlobalAdmin) {
			navigationContext.setSection(currentSection as any);
		}
	});

	// Data loading functions (shared across views)
	async function loadTopicsFromDb(recalculate: boolean = false) {
		try {
			topicsLoading = true;
			if (recalculate) {
				try {
					await recalculateAllTopicStats();
				} catch (e) {
					console.error('Failed to recalculate topic stats:', e);
				}
			}
			const topics = await getTopics();
			dbTopics.set(topics);
			allTopics.set(topics.map(t => ({ id: t.slug, label: t.title })));
		} catch (e) {
			console.error('Error loading topics:', e);
			allTopics.set([]);
			dbTopics.set([]);
		} finally {
			topicsLoading = false;
		}
	}

	async function loadData() {
		try {
			loading.set(true);
			error.set('');

			await loadTopicsFromDb();

			const [usersData, groupsData] = await Promise.all([
				getAdminUsers(),
				getAdminGroups()
			]);
			users.set(usersData.sort((a: any, b: any) => a.email.localeCompare(b.email)));
			groups.set(groupsData.sort((a: any, b: any) => a.name.localeCompare(b.name)));
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to load admin data');
			console.error('Error loading admin data:', e);
		} finally {
			loading.set(false);
		}
	}

	async function loadGlobalResources() {
		try {
			resourcesLoading = true;
			error.set('');
			const response = await getGlobalResources();
			resources.set(response.resources);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to load global resources');
			console.error('Error loading global resources:', e);
		} finally {
			resourcesLoading = false;
		}
	}

	async function loadPrompts() {
		try {
			promptsLoading = true;
			error.set('');
			const promptsData = await getPromptModules();
			prompts.set(promptsData);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to load prompts');
			console.error('Error loading prompts:', e);
		} finally {
			promptsLoading = false;
		}
	}

	async function loadAvailableTonalities() {
		try {
			const tonalities = await getTonalities();
			availableTonalities.set(tonalities);
		} catch (e) {
			console.error('Failed to load tonalities:', e);
		}
	}

	// Load view-specific data based on current route
	$effect(() => {
		if (currentView === 'resources' && $resources.length === 0) {
			loadGlobalResources();
		}
		if (currentView === 'prompts' && $prompts.length === 0) {
			loadPrompts();
		}
		if (currentView === 'topics' && $dbTopics.length === 0) {
			loadTopicsFromDb(true);
		}
	});

	// Expose reload functions via context
	setContext('rootAdminLoadData', loadData);
	setContext('rootAdminLoadTopics', loadTopicsFromDb);
	setContext('rootAdminLoadResources', loadGlobalResources);
	setContext('rootAdminLoadPrompts', loadPrompts);
	setContext('rootAdminLoadTonalities', loadAvailableTonalities);

	// Action handlers for chat-triggered UI actions
	let actionUnsubscribers: (() => void)[] = [];

	async function handleSwitchGlobalViewAction(action: UIAction): Promise<ActionResult> {
		const view = action.params?.view;
		if (!view) {
			return { success: false, action: 'switch_global_view', error: 'No view specified' };
		}
		goto(`/root/${view}`);
		return { success: true, action: 'switch_global_view', message: `Switched to ${view} view` };
	}

	async function handleSelectTopicAction(action: UIAction): Promise<ActionResult> {
		const topicSlug = action.params?.topic;
		if (!topicSlug) {
			return { success: false, action: 'select_topic', error: 'No topic specified' };
		}
		goto(`/admin/${topicSlug}`);
		return { success: true, action: 'select_topic', message: `Navigating to topic admin: ${topicSlug}` };
	}

	onMount(() => {
		if (!$auth.isAuthenticated) {
			goto('/');
			return;
		}
		loadData();

		actionUnsubscribers.push(
			actionStore.registerHandler('switch_global_view', handleSwitchGlobalViewAction),
			actionStore.registerHandler('select_topic', handleSelectTopicAction)
		);
	});

	onDestroy(() => {
		actionUnsubscribers.forEach(unsub => unsub());
	});
</script>

<div class="admin-container" data-testid="global-admin-panel">
	<div class="admin-header">
		<div class="header-left">
			<h1>Global Administration</h1>
		</div>
		<nav class="admin-actions">
			<a
				href="/root/users"
				class="action-btn"
				class:active={currentView === 'users'}
			>
				Users
			</a>
			<a
				href="/root/groups"
				class="action-btn"
				class:active={currentView === 'groups'}
			>
				Groups
			</a>
			<a
				href="/root/prompts"
				class="action-btn"
				class:active={currentView === 'prompts'}
			>
				Prompts
			</a>
			<a
				href="/root/resources"
				class="action-btn"
				class:active={currentView === 'resources'}
			>
				Resources
			</a>
			<a
				href="/root/topics"
				class="action-btn"
				class:active={currentView === 'topics'}
			>
				Topics
			</a>
			<a
				href="/root/tonalities"
				class="action-btn"
				class:active={currentView === 'tonalities'}
			>
				Tonalities
			</a>
		</nav>
	</div>

	{#if $error}
		<div class="error-message">{$error}</div>
	{/if}

	{#if $loading}
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

	.header-left h1 {
		margin: 0;
		font-size: 1.25rem;
		font-weight: 600;
		color: #1f2937;
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

	.error-message {
		background: #fef2f2;
		color: #dc2626;
		padding: 1rem;
		margin: 0 2rem 1rem;
		border-radius: 6px;
		border: 1px solid #fecaca;
	}
</style>
