<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { PromptModule } from '$lib/api';

	// Get shared state from layout context
	const prompts = getContext<Writable<PromptModule[]>>('rootAdminPrompts');
	const loading = getContext<Writable<boolean>>('rootAdminLoading');
</script>

<div class="view">
	<div class="view-header">
		<h2>Prompts Management</h2>
	</div>

	{#if $loading}
		<p class="loading-text">Loading prompts...</p>
	{:else if $prompts.length === 0}
		<p class="empty-text">No prompts found.</p>
	{:else}
		<div class="content-card">
			<p class="description">Manage system prompts and prompt modules.</p>
			<div class="prompts-list">
				{#each $prompts as prompt}
					<div class="prompt-item">
						<div class="prompt-header">
							<span class="prompt-name">{prompt.name}</span>
							<span class="prompt-type">{prompt.module_type}</span>
						</div>
						{#if prompt.description}
							<p class="prompt-description">{prompt.description}</p>
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

	.prompts-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.prompt-item {
		padding: 1rem;
		background: #f9fafb;
		border-radius: 6px;
	}

	.prompt-header {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 0.5rem;
	}

	.prompt-name {
		font-weight: 500;
		color: #1f2937;
	}

	.prompt-type {
		padding: 0.125rem 0.5rem;
		background: #e0f2fe;
		color: #0369a1;
		border-radius: 4px;
		font-size: 0.75rem;
	}

	.prompt-description {
		margin: 0;
		color: #6b7280;
		font-size: 0.875rem;
	}
</style>
