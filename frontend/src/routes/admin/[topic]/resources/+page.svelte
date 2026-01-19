<script lang="ts">
	import { page } from '$app/stores';
	import { getGroupResources, deleteResource, type Resource } from '$lib/api';
	import { onMount, onDestroy } from 'svelte';
	import { actionStore, type UIAction, type ActionResult } from '$lib/stores/actions';
	import ResourceEditor from '$lib/components/ResourceEditor.svelte';

	let topic = $derived($page.params.topic);
	let resources: Resource[] = $state([]);
	let loading = $state(true);
	let error = $state('');
	let showUploadModal = $state(false);

	async function loadResources() {
		try {
			loading = true;
			error = '';
			const response = await getGroupResources(topic);
			resources = response.resources;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load resources';
		} finally {
			loading = false;
		}
	}

	async function handleDelete(resourceId: number) {
		if (!confirm('Delete this resource?')) return;
		try {
			await deleteResource(resourceId);
			await loadResources();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to delete';
		}
	}

	function handleUploadComplete() {
		showUploadModal = false;
		loadResources();
	}

	// Action handlers
	let actionUnsubscribers: (() => void)[] = [];

	onMount(() => {
		loadResources();

		actionUnsubscribers.push(
			actionStore.registerHandler('delete_resource', async (action: UIAction): Promise<ActionResult> => {
				const id = action.params?.resource_id;
				if (!id) return { success: false, action: 'delete_resource', error: 'No resource_id' };
				if (!action.params?.confirmed) return { success: false, action: 'delete_resource', error: 'Requires confirmation' };
				await deleteResource(id);
				await loadResources();
				return { success: true, action: 'delete_resource', message: 'Resource deleted' };
			}),
			actionStore.registerHandler('upload_resource', async (): Promise<ActionResult> => {
				showUploadModal = true;
				return { success: true, action: 'upload_resource', message: 'Upload modal opened' };
			})
		);
	});

	onDestroy(() => {
		actionUnsubscribers.forEach((unsub) => unsub());
	});
</script>

<div class="resources-view">
	{#if error}
		<div class="error-message">{error}</div>
	{/if}

	<div class="view-header">
		<h2>Resource Management</h2>
		<button class="btn-primary" onclick={() => (showUploadModal = true)}>Upload Resource</button>
	</div>

	{#if loading}
		<div class="loading">Loading resources...</div>
	{:else if resources.length === 0}
		<div class="empty-state">No resources found for this topic.</div>
	{:else}
		<div class="resources-grid">
			{#each resources as resource}
				<div class="resource-card">
					<div class="resource-header">
						<span class="resource-type">{resource.resource_type}</span>
						<button class="btn-sm btn-danger" onclick={() => handleDelete(resource.id)}>
							Delete
						</button>
					</div>
					<h3>{resource.title || resource.name}</h3>
					{#if resource.description}
						<p class="resource-desc">{resource.description}</p>
					{/if}
					{#if resource.url}
						<a href={resource.url} target="_blank" rel="noopener" class="resource-link">
							View Resource
						</a>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>

{#if showUploadModal}
	<div class="modal-overlay" onclick={() => (showUploadModal = false)}>
		<div class="modal" onclick={(e) => e.stopPropagation()}>
			<h3>Upload Resource</h3>
			<ResourceEditor topic={topic} onComplete={handleUploadComplete} />
			<button class="btn-secondary" onclick={() => (showUploadModal = false)}>Cancel</button>
		</div>
	</div>
{/if}

<style>
	.resources-view {
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

	.btn-primary {
		padding: 0.5rem 1rem;
		background: #6366f1;
		color: white;
		border: none;
		border-radius: 6px;
		cursor: pointer;
		font-size: 0.875rem;
	}

	.error-message {
		background: #fef2f2;
		color: #dc2626;
		padding: 1rem;
		margin-bottom: 1rem;
		border-radius: 6px;
		border: 1px solid #fecaca;
	}

	.loading, .empty-state {
		text-align: center;
		padding: 3rem;
		color: #6b7280;
	}

	.resources-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
		gap: 1rem;
	}

	.resource-card {
		background: white;
		border: 1px solid #e5e7eb;
		border-radius: 8px;
		padding: 1rem;
	}

	.resource-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	.resource-type {
		font-size: 0.75rem;
		font-weight: 500;
		color: #6b7280;
		text-transform: uppercase;
	}

	.resource-card h3 {
		margin: 0 0 0.5rem;
		font-size: 1rem;
		color: #1f2937;
	}

	.resource-desc {
		font-size: 0.875rem;
		color: #6b7280;
		margin: 0 0 0.5rem;
	}

	.resource-link {
		font-size: 0.875rem;
		color: #6366f1;
	}

	.btn-sm {
		padding: 0.25rem 0.5rem;
		background: #f3f4f6;
		border: 1px solid #e5e7eb;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.75rem;
	}

	.btn-danger {
		background: #fef2f2;
		border-color: #fecaca;
		color: #dc2626;
	}

	.modal-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.5);
		display: flex;
		justify-content: center;
		align-items: center;
		z-index: 1000;
	}

	.modal {
		background: white;
		padding: 2rem;
		border-radius: 8px;
		min-width: 500px;
		max-width: 90vw;
	}

	.modal h3 {
		margin: 0 0 1.5rem;
	}

	.btn-secondary {
		margin-top: 1rem;
		padding: 0.5rem 1rem;
		background: white;
		color: #6b7280;
		border: 1px solid #e5e7eb;
		border-radius: 6px;
		cursor: pointer;
	}
</style>
