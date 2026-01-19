<script lang="ts">
	import { page } from '$app/stores';
	import { getAdminArticles, deleteArticle, reactivateArticle, recallArticle, purgeArticle } from '$lib/api';
	import { onMount, onDestroy } from 'svelte';
	import { actionStore, type UIAction, type ActionResult } from '$lib/stores/actions';

	let topic = $derived($page.params.topic);
	let articles: any[] = $state([]);
	let loading = $state(true);
	let error = $state('');

	async function loadArticles() {
		try {
			loading = true;
			error = '';
			articles = await getAdminArticles(topic);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load articles';
		} finally {
			loading = false;
		}
	}

	async function handleDeactivate(articleId: number) {
		if (!confirm('Deactivate this article?')) return;
		try {
			await deleteArticle(articleId);
			await loadArticles();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to deactivate';
		}
	}

	async function handleReactivate(articleId: number) {
		try {
			await reactivateArticle(articleId);
			await loadArticles();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to reactivate';
		}
	}

	async function handleRecall(articleId: number) {
		if (!confirm('Recall this article to draft?')) return;
		try {
			await recallArticle(articleId);
			await loadArticles();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to recall';
		}
	}

	async function handlePurge(articleId: number) {
		if (!confirm('PERMANENTLY delete this article? This cannot be undone.')) return;
		try {
			await purgeArticle(articleId);
			await loadArticles();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to purge';
		}
	}

	// Action handlers
	let actionUnsubscribers: (() => void)[] = [];

	onMount(() => {
		loadArticles();

		actionUnsubscribers.push(
			actionStore.registerHandler('deactivate_article', async (action: UIAction): Promise<ActionResult> => {
				const id = action.params?.article_id;
				if (!id) return { success: false, action: 'deactivate_article', error: 'No article_id' };
				if (!action.params?.confirmed) return { success: false, action: 'deactivate_article', error: 'Requires confirmation' };
				await deleteArticle(id);
				await loadArticles();
				return { success: true, action: 'deactivate_article', message: 'Article deactivated' };
			}),
			actionStore.registerHandler('reactivate_article', async (action: UIAction): Promise<ActionResult> => {
				const id = action.params?.article_id;
				if (!id) return { success: false, action: 'reactivate_article', error: 'No article_id' };
				await reactivateArticle(id);
				await loadArticles();
				return { success: true, action: 'reactivate_article', message: 'Article reactivated' };
			}),
			actionStore.registerHandler('recall_article', async (action: UIAction): Promise<ActionResult> => {
				const id = action.params?.article_id;
				if (!id) return { success: false, action: 'recall_article', error: 'No article_id' };
				if (!action.params?.confirmed) return { success: false, action: 'recall_article', error: 'Requires confirmation' };
				await recallArticle(id);
				await loadArticles();
				return { success: true, action: 'recall_article', message: 'Article recalled to draft' };
			}),
			actionStore.registerHandler('purge_article', async (action: UIAction): Promise<ActionResult> => {
				const id = action.params?.article_id;
				if (!id) return { success: false, action: 'purge_article', error: 'No article_id' };
				if (!action.params?.confirmed) return { success: false, action: 'purge_article', error: 'Requires confirmation' };
				await purgeArticle(id);
				await loadArticles();
				return { success: true, action: 'purge_article', message: 'Article permanently deleted' };
			})
		);
	});

	onDestroy(() => {
		actionUnsubscribers.forEach((unsub) => unsub());
	});

	function formatDate(dateString: string) {
		return new Date(dateString).toLocaleDateString();
	}

	function getStatusBadgeClass(status: string) {
		switch (status) {
			case 'published': return 'status-published';
			case 'editor': return 'status-editor';
			case 'draft': return 'status-draft';
			case 'inactive': return 'status-inactive';
			default: return '';
		}
	}
</script>

<div class="articles-view" data-testid="admin-content-panel">
	{#if error}
		<div class="error-message">{error}</div>
	{/if}

	<div class="view-header">
		<h2>Article Management</h2>
	</div>

	{#if loading}
		<div class="loading">Loading articles...</div>
	{:else if articles.length === 0}
		<div class="empty-state">No articles found for this topic.</div>
	{:else}
		<div class="articles-table" data-testid="admin-article-list">
			<table>
				<thead>
					<tr>
						<th>ID</th>
						<th>Headline</th>
						<th>Status</th>
						<th>Author</th>
						<th>Created</th>
						<th>Actions</th>
					</tr>
				</thead>
				<tbody>
					{#each articles as article}
						<tr class:inactive={article.status === 'inactive'}>
							<td>{article.id}</td>
							<td>{article.headline}</td>
							<td>
								<span class="status-badge {getStatusBadgeClass(article.status)}">
									{article.status}
								</span>
							</td>
							<td>{article.author || 'Unknown'}</td>
							<td>{formatDate(article.created_at)}</td>
							<td>
								<div class="action-buttons">
									{#if article.status === 'inactive'}
										<button class="btn-sm btn-success" onclick={() => handleReactivate(article.id)}>
											Reactivate
										</button>
									{:else}
										<button class="btn-sm btn-warning" onclick={() => handleDeactivate(article.id)}>
											Deactivate
										</button>
									{/if}
									{#if article.status === 'published'}
										<button class="btn-sm" onclick={() => handleRecall(article.id)}>
											Recall
										</button>
									{/if}
									<button class="btn-sm btn-danger" onclick={() => handlePurge(article.id)}>
										Purge
									</button>
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>

<style>
	.articles-view {
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

	.articles-table {
		background: white;
		border: 1px solid #e5e7eb;
		border-radius: 8px;
		overflow: hidden;
	}

	table {
		width: 100%;
		border-collapse: collapse;
	}

	th, td {
		padding: 0.75rem 1rem;
		text-align: left;
		border-bottom: 1px solid #e5e7eb;
	}

	th {
		background: #f9fafb;
		font-weight: 600;
		color: #374151;
		font-size: 0.875rem;
	}

	tr.inactive {
		background: #f9fafb;
		opacity: 0.7;
	}

	.status-badge {
		padding: 0.25rem 0.5rem;
		border-radius: 4px;
		font-size: 0.75rem;
		font-weight: 500;
	}

	.status-published { background: #dcfce7; color: #166534; }
	.status-editor { background: #fef3c7; color: #92400e; }
	.status-draft { background: #e0f2fe; color: #0369a1; }
	.status-inactive { background: #f3f4f6; color: #6b7280; }

	.action-buttons {
		display: flex;
		gap: 0.5rem;
	}

	.btn-sm {
		padding: 0.25rem 0.5rem;
		background: #f3f4f6;
		border: 1px solid #e5e7eb;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.75rem;
	}

	.btn-sm:hover { background: #e5e7eb; }
	.btn-warning { background: #fef3c7; border-color: #fcd34d; color: #92400e; }
	.btn-success { background: #dcfce7; border-color: #86efac; color: #166534; }
	.btn-danger { background: #fef2f2; border-color: #fecaca; color: #dc2626; }
</style>
