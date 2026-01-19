<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';

	// Redirect /admin/[topic] to /admin/[topic]/articles as per sections.json
	let topic = $page.params.topic;

	onMount(() => {
		if (browser) {
			goto(`/admin/${topic}/articles`, { replaceState: true });
		}
	});
</script>

<div class="redirect">Redirecting to articles...</div>

<style>
	.redirect {
		display: flex;
		justify-content: center;
		align-items: center;
		padding: 3rem;
		color: #6b7280;
	}
</style>
