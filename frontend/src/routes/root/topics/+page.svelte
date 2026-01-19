<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { Topic } from '$lib/api';

	// Get shared state from layout context
	const dbTopics = getContext<Writable<Topic[]>>('rootAdminDbTopics');
	const loading = getContext<Writable<boolean>>('rootAdminLoading');
</script>

<div class="view">
	<div class="view-header">
		<h2>Topics Management</h2>
	</div>

	{#if $loading}
		<p class="loading-text">Loading topics...</p>
	{:else if $dbTopics.length === 0}
		<p class="empty-text">No topics found.</p>
	{:else}
		<div class="content-card">
			<p class="description">Manage content topics and their configurations.</p>
			<div class="topics-list" data-testid="topics-list">
				{#each $dbTopics as topic}
					<div class="topic-item" data-testid="topic-item">
						<div class="topic-header">
							<span class="topic-title">{topic.title}</span>
							<span class="topic-slug">{topic.slug}</span>
						</div>
						{#if topic.description}
							<p class="topic-description">{topic.description}</p>
						{/if}
						<div class="topic-stats">
							{#if topic.article_count !== undefined}
								<span class="stat">Articles: {topic.article_count}</span>
							{/if}
							{#if topic.resource_count !== undefined}
								<span class="stat">Resources: {topic.resource_count}</span>
							{/if}
						</div>
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

	.topics-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.topic-item {
		padding: 1rem;
		background: #f9fafb;
		border-radius: 6px;
	}

	.topic-header {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 0.5rem;
	}

	.topic-title {
		font-weight: 500;
		color: #1f2937;
	}

	.topic-slug {
		padding: 0.125rem 0.5rem;
		background: #f3e8ff;
		color: #7c3aed;
		border-radius: 4px;
		font-size: 0.75rem;
		font-family: monospace;
	}

	.topic-description {
		margin: 0 0 0.5rem;
		color: #6b7280;
		font-size: 0.875rem;
	}

	.topic-stats {
		display: flex;
		gap: 1rem;
	}

	.stat {
		color: #6b7280;
		font-size: 0.75rem;
	}
</style>
