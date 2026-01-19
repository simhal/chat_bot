<script lang="ts">
	import { page } from '$app/stores';
	import { getPromptModules, updatePromptModule, type PromptModule } from '$lib/api';
	import { onMount, onDestroy } from 'svelte';
	import { actionStore, type UIAction, type ActionResult } from '$lib/stores/actions';

	let topic = $derived($page.params.topic);
	let prompts: PromptModule[] = $state([]);
	let loading = $state(true);
	let error = $state('');

	// Edit state
	let editingPrompt: PromptModule | null = $state(null);
	let editedText = $state('');
	let saving = $state(false);

	async function loadPrompts() {
		try {
			loading = true;
			error = '';
			const allPrompts = await getPromptModules();
			// Filter to topic-specific prompts
			prompts = allPrompts.filter(
				(p) => p.topic === topic || (p.module_type === 'content_topic' && p.topic === topic)
			);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load prompts';
		} finally {
			loading = false;
		}
	}

	function startEdit(prompt: PromptModule) {
		editingPrompt = prompt;
		editedText = prompt.template_text;
	}

	function cancelEdit() {
		editingPrompt = null;
		editedText = '';
	}

	async function savePrompt() {
		if (!editingPrompt) return;
		try {
			saving = true;
			error = '';
			await updatePromptModule(editingPrompt.id, {
				template_text: editedText
			});
			await loadPrompts();
			editingPrompt = null;
			editedText = '';
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to save prompt';
		} finally {
			saving = false;
		}
	}

	// Action handlers
	let actionUnsubscribers: (() => void)[] = [];

	onMount(() => {
		loadPrompts();

		actionUnsubscribers.push(
			actionStore.registerHandler('edit_prompt', async (action: UIAction): Promise<ActionResult> => {
				const promptId = action.params?.prompt_id;
				if (!promptId) return { success: false, action: 'edit_prompt', error: 'No prompt_id' };
				const prompt = prompts.find((p) => p.id === promptId);
				if (!prompt) return { success: false, action: 'edit_prompt', error: 'Prompt not found' };
				startEdit(prompt);
				return { success: true, action: 'edit_prompt', message: 'Editing prompt' };
			}),
			actionStore.registerHandler('save_prompt', async (): Promise<ActionResult> => {
				if (!editingPrompt) return { success: false, action: 'save_prompt', error: 'No prompt being edited' };
				await savePrompt();
				return { success: true, action: 'save_prompt', message: 'Prompt saved' };
			})
		);
	});

	onDestroy(() => {
		actionUnsubscribers.forEach((unsub) => unsub());
	});
</script>

<div class="prompts-view">
	{#if error}
		<div class="error-message">{error}</div>
	{/if}

	<div class="view-header">
		<h2>Topic Prompts</h2>
	</div>

	{#if loading}
		<div class="loading">Loading prompts...</div>
	{:else if prompts.length === 0}
		<div class="empty-state">No topic-specific prompts found.</div>
	{:else}
		<div class="prompts-list">
			{#each prompts as prompt}
				<div class="prompt-card">
					<div class="prompt-header">
						<h3>{prompt.name}</h3>
						<span class="prompt-type">{prompt.module_type}</span>
					</div>
					{#if prompt.description}
						<p class="prompt-desc">{prompt.description}</p>
					{/if}
					<div class="prompt-preview">
						{prompt.template_text.substring(0, 200)}{prompt.template_text.length > 200 ? '...' : ''}
					</div>
					<button class="btn-sm" onclick={() => startEdit(prompt)}>Edit</button>
				</div>
			{/each}
		</div>
	{/if}
</div>

{#if editingPrompt}
	<div class="modal-overlay" onclick={cancelEdit}>
		<div class="modal" onclick={(e) => e.stopPropagation()}>
			<h3>Edit Prompt: {editingPrompt.name}</h3>
			<div class="form-group">
				<label for="prompt-text">Template Text</label>
				<textarea id="prompt-text" bind:value={editedText} rows="15"></textarea>
			</div>
			<div class="modal-actions">
				<button onclick={savePrompt} disabled={saving}>
					{saving ? 'Saving...' : 'Save'}
				</button>
				<button class="btn-secondary" onclick={cancelEdit}>Cancel</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.prompts-view {
		padding: 0 2rem 2rem;
	}

	.view-header {
		margin-bottom: 1.5rem;
	}

	.view-header h2 {
		margin: 0;
		font-size: 1.25rem;
		color: #1f2937;
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

	.prompts-list {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.prompt-card {
		background: white;
		border: 1px solid #e5e7eb;
		border-radius: 8px;
		padding: 1.5rem;
	}

	.prompt-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	.prompt-header h3 {
		margin: 0;
		font-size: 1rem;
		color: #1f2937;
	}

	.prompt-type {
		font-size: 0.75rem;
		font-weight: 500;
		color: #6b7280;
		text-transform: uppercase;
		padding: 0.25rem 0.5rem;
		background: #f3f4f6;
		border-radius: 4px;
	}

	.prompt-desc {
		font-size: 0.875rem;
		color: #6b7280;
		margin: 0 0 0.75rem;
	}

	.prompt-preview {
		font-family: monospace;
		font-size: 0.75rem;
		color: #374151;
		background: #f9fafb;
		padding: 0.75rem;
		border-radius: 4px;
		margin-bottom: 0.75rem;
		white-space: pre-wrap;
	}

	.btn-sm {
		padding: 0.25rem 0.75rem;
		background: #f3f4f6;
		border: 1px solid #e5e7eb;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.75rem;
	}

	.btn-sm:hover {
		background: #e5e7eb;
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
		width: 90vw;
		max-width: 800px;
		max-height: 90vh;
		overflow-y: auto;
	}

	.modal h3 {
		margin: 0 0 1.5rem;
	}

	.form-group {
		margin-bottom: 1rem;
	}

	.form-group label {
		display: block;
		margin-bottom: 0.5rem;
		font-weight: 500;
		color: #374151;
	}

	.form-group textarea {
		width: 100%;
		padding: 0.75rem;
		border: 1px solid #e5e7eb;
		border-radius: 4px;
		font-family: monospace;
		font-size: 0.875rem;
		resize: vertical;
	}

	.modal-actions {
		display: flex;
		gap: 0.5rem;
		margin-top: 1.5rem;
	}

	.modal-actions button {
		padding: 0.5rem 1rem;
		border-radius: 6px;
		cursor: pointer;
	}

	.modal-actions button:first-child {
		background: #6366f1;
		color: white;
		border: none;
	}

	.modal-actions button:first-child:disabled {
		background: #c7d2fe;
	}

	.btn-secondary {
		background: white;
		color: #6b7280;
		border: 1px solid #e5e7eb;
	}
</style>
