<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { TonalityOption } from '$lib/api';

	// Get shared state from layout context
	const availableTonalities = getContext<Writable<TonalityOption[]>>('rootAdminTonalities');
	const loading = getContext<Writable<boolean>>('rootAdminLoading');
</script>

<div class="view">
	<div class="view-header">
		<h2>Tonalities Management</h2>
	</div>

	{#if $loading}
		<p class="loading-text">Loading tonalities...</p>
	{:else if $availableTonalities.length === 0}
		<p class="empty-text">No tonalities found.</p>
	{:else}
		<div class="content-card">
			<p class="description">Manage available tonality options for chat and content generation.</p>
			<div class="tonalities-list" data-testid="tonality-list">
				{#each $availableTonalities as tonality}
					<div class="tonality-item" data-testid="tonality-item">
						<div class="tonality-header">
							<span class="tonality-name">{tonality.name}</span>
							{#if tonality.id}
								<span class="tonality-id">ID: {tonality.id}</span>
							{/if}
						</div>
						{#if tonality.description}
							<p class="tonality-description">{tonality.description}</p>
						{/if}
					</div>
				{/each}
			</div>
		</div>
	{/if}
</div>

<style>
	.view {
		padding: 0 2rem 2rem;
	}

	.view-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1.5rem;
	}

	.view-header h2 {
		margin: 0;
		font-size: 1.25rem;
		color: #1f2937;
	}

	.loading-text,
	.empty-text {
		color: #6b7280;
		text-align: center;
		padding: 2rem;
	}

	.content-card {
		background: white;
		border: 1px solid #e5e7eb;
		border-radius: 8px;
		padding: 1.5rem;
	}

	.description {
		color: #6b7280;
		margin: 0 0 1rem;
	}

	.tonalities-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.tonality-item {
		padding: 1rem;
		background: #f9fafb;
		border-radius: 6px;
	}

	.tonality-header {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 0.5rem;
	}

	.tonality-name {
		font-weight: 500;
		color: #1f2937;
	}

	.tonality-id {
		padding: 0.125rem 0.5rem;
		background: #fef3c7;
		color: #92400e;
		border-radius: 4px;
		font-size: 0.75rem;
	}

	.tonality-description {
		margin: 0;
		color: #6b7280;
		font-size: 0.875rem;
	}
</style>
