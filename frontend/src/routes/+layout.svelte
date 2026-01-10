<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { get } from 'svelte/store';
	import favicon from '$lib/assets/favicon.svg';
	import Header from '$lib/components/Header.svelte';
	import SplitPane from '$lib/components/SplitPane.svelte';
	import ChatPanel from '$lib/components/ChatPanel.svelte';
	import { actionStore } from '$lib/stores/actions';

	let { children } = $props();

	// Store unsubscribe functions for cleanup
	let unsubscribers: (() => void)[] = [];

	onMount(() => {
		// Register global navigation handlers - available from any page
		// These emulate button clicks for better UX (tab highlights, context updates)

		unsubscribers.push(
			actionStore.registerHandler('goto_home', async (action) => {
				const topic = action.params?.topic;
				console.log('🏠 goto_home handler: topic =', topic);
				// Always navigate with URL - the reactive handleDeepLink will switch tabs
				await goto(topic ? `/?tab=${topic}` : '/', { invalidateAll: true });
				return { success: true, action: 'goto_home' };
			})
		);

		unsubscribers.push(
			actionStore.registerHandler('goto_search', async (action) => {
				console.log('🔍 goto_search handler');
				await goto('/?tab=search', { invalidateAll: true });
				return { success: true, action: 'goto_search' };
			})
		);

		unsubscribers.push(
			actionStore.registerHandler('goto_analyst', async (action) => {
				const topic = action.params?.topic;
				await goto(topic ? `/analyst/${topic}` : '/analyst');
				return { success: true, action: 'goto_analyst' };
			})
		);

		unsubscribers.push(
			actionStore.registerHandler('goto_editor', async (action) => {
				const topic = action.params?.topic;
				await goto(topic ? `/editor/${topic}` : '/editor');
				return { success: true, action: 'goto_editor' };
			})
		);

		unsubscribers.push(
			actionStore.registerHandler('goto_topic_admin', async (action) => {
				const topic = action.params?.topic;
				console.log('📁 goto_topic_admin handler: topic =', topic);
				await goto(topic ? `/admin?topic=${topic}` : '/admin');
				return { success: true, action: 'goto_topic_admin' };
			})
		);

		unsubscribers.push(
			actionStore.registerHandler('goto_admin_global', async (action) => {
				await goto('/admin/global');
				return { success: true, action: 'goto_admin_global' };
			})
		);

		unsubscribers.push(
			actionStore.registerHandler('goto_profile', async (action) => {
				await goto('/profile');
				return { success: true, action: 'goto_profile' };
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
