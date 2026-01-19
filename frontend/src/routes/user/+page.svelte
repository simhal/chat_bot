<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';

	// Redirect /user to /user/profile as per sections.json
	onMount(() => {
		if (browser) {
			goto('/user/profile', { replaceState: true });
		}
	});
</script>

<div class="redirect">Redirecting to profile...</div>

<style>
	.redirect {
		display: flex;
		justify-content: center;
		align-items: center;
		height: 100vh;
		color: #6b7280;
	}
</style>
