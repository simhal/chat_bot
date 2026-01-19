<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { Resource } from '$lib/api';

	// Get shared state from layout context
	const resources = getContext<Writable<Resource[]>>('rootAdminResources');
	const loading = getContext<Writable<boolean>>('rootAdminLoading');
</script>

<div class="view">
	<div class="view-header">
		<h2>Resources Management</h2>
	</div>

	{#if $loading}
		<p class="loading-text">Loading resources...</p>
	{:else if $resources.length === 0}
		<p class="empty-text">No global resources found.</p>
	{:else}
		<div class="content-card">
			<p class="description">Manage global resources available across all topics.</p>
			<div class="resources-list">
				{#each $resources as resource}
					<div class="resource-item">
						<div class="resource-header">
							<span class="resource-title">{resource.title}</span>
							<span class="resource-type">{resource.resource_type}</span>
						</div>
						{#if resource.description}
							<p class="resource-description">{resource.description}</p>
						{/if}
						{#if resource.url}
							<a href={resource.url} target="_blank" rel="noopener noreferrer" class="resource-link">
								{resource.url}
							</a>
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

	.resources-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.resource-item {
		padding: 1rem;
		background: #f9fafb;
		border-radius: 6px;
	}

	.resource-header {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 0.5rem;
	}

	.resource-title {
		font-weight: 500;
		color: #1f2937;
	}

	.resource-type {
		padding: 0.125rem 0.5rem;
		background: #dbeafe;
		color: #1d4ed8;
		border-radius: 4px;
		font-size: 0.75rem;
	}

	.resource-description {
		margin: 0 0 0.5rem;
		color: #6b7280;
		font-size: 0.875rem;
	}

	.resource-link {
		color: #6366f1;
		font-size: 0.875rem;
		text-decoration: none;
	}

	.resource-link:hover {
		text-decoration: underline;
	}
</style>
