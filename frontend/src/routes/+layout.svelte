<script lang="ts">
	import favicon from '$lib/assets/favicon.svg';
	import Header from '$lib/components/Header.svelte';
	import SplitPane from '$lib/components/SplitPane.svelte';
	import ChatPanel from '$lib/components/ChatPanel.svelte';

	let { children } = $props();
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
