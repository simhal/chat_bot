<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';

	// Redirect /root to /root/users as per sections.json
	onMount(() => {
		if (browser) {
			goto('/root/users', { replaceState: true });
		}
	});
</script>

<div class="redirect">Redirecting to user management...</div>

<style>
	.redirect {
		display: flex;
		justify-content: center;
		align-items: center;
		padding: 3rem;
		color: #6b7280;
	}
</style>
