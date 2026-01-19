<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';

	// Get shared state from layout context
	const groups = getContext<Writable<any[]>>('rootAdminGroups');
	const loading = getContext<Writable<boolean>>('rootAdminLoading');
</script>

<div class="view">
	<div class="view-header">
		<h2>Groups Management</h2>
	</div>

	{#if $loading}
		<p class="loading-text">Loading groups...</p>
	{:else if $groups.length === 0}
		<p class="empty-text">No groups found.</p>
	{:else}
		<div class="content-card">
			<p class="description">Manage user groups and their permissions.</p>
			<div class="groups-list">
				{#each $groups as group}
					<div class="group-item">
						<span class="group-name">{group.name}</span>
						{#if group.description}
							<span class="group-description">{group.description}</span>
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

	.groups-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.group-item {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 0.75rem 1rem;
		background: #f9fafb;
		border-radius: 6px;
	}

	.group-name {
		font-weight: 500;
		color: #1f2937;
	}

	.group-description {
		color: #6b7280;
		font-size: 0.875rem;
	}
</style>
