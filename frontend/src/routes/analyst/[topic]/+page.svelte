<script lang="ts">
    import { page } from '$app/stores';
    import { auth } from '$lib/stores/auth';
    import { getAnalystDraftArticles, deleteArticle, reactivateArticle, generateContent, downloadArticlePDF, approveArticle, getGroupResources, type Resource } from '$lib/api';
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import Markdown from '$lib/components/Markdown.svelte';
    import ResourceEditor from '$lib/components/ResourceEditor.svelte';

    type Topic = 'macro' | 'equity' | 'fixed_income' | 'esg';

    interface Article {
        id: number;
        topic: string;
        headline: string;
        content: string;
        readership_count: number;
        rating: number | null;
        rating_count: number;
        keywords: string | null;
        status: string;  // draft, editor, or published
        created_at: string;
        updated_at: string;
        created_by_agent: string;
        is_active: boolean;
    }

    let currentTopic: Topic;
    let articles: Article[] = [];
    let loading = true;
    let error = '';
    let selectedArticle: Article | null = null;
    let showGenerateModal = false;
    let generateQuery = '';
    let isGenerating = false;

    // Resources for generation
    let generateResources: Resource[] = [];
    let resourcesLoading = false;

    const topics = [
        { id: 'macro' as Topic, label: 'Macroeconomic' },
        { id: 'equity' as Topic, label: 'Equity' },
        { id: 'fixed_income' as Topic, label: 'Fixed Income' },
        { id: 'esg' as Topic, label: 'ESG' }
    ];

    const topicLabels: Record<Topic, string> = {
        'macro': 'Macroeconomic Research',
        'equity': 'Equity Research',
        'fixed_income': 'Fixed Income Research',
        'esg': 'ESG Research'
    };

    // Get topic from URL parameter
    $: currentTopic = $page.params.topic as Topic;

    function switchTopic(topic: Topic) {
        goto(`/analyst/${topic}`);
    }

    // Check if user can access this topic - only analyst role grants access
    function canAccessTopic(topic: string): boolean {
        if (!$auth.user?.scopes) return false;
        return $auth.user.scopes.includes(`${topic}:analyst`);
    }

    // Filter topics to only show those the user has analyst access to
    $: accessibleTopics = topics.filter(topic => canAccessTopic(topic.id));

    // Redirect if user doesn't have permission
    $: if ($auth.isAuthenticated && currentTopic && !canAccessTopic(currentTopic)) {
        goto('/analyst');
    }

    async function loadArticles() {
        if (!currentTopic) return;

        try {
            loading = true;
            error = '';
            articles = await getAnalystDraftArticles(currentTopic);
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to load articles';
            console.error('Error loading articles:', e);
        } finally {
            loading = false;
        }
    }

    async function handleDeleteArticle(articleId: number) {
        if (!confirm('Are you sure you want to delete this article?')) return;

        try {
            error = '';
            await deleteArticle(articleId);
            await loadArticles();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to delete article';
        }
    }

    async function handleSubmitArticle(articleId: number) {
        try {
            error = '';
            await approveArticle(articleId);
            await loadArticles();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to approve article';
        }
    }

    async function handleReactivateArticle(articleId: number) {
        try {
            error = '';
            await reactivateArticle(articleId);
            await loadArticles();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to reactivate article';
        }
    }

    function navigateToEditor(articleId: number) {
        goto(`/analyst/edit/${articleId}`);
    }

    async function loadGenerateResources() {
        try {
            resourcesLoading = true;
            // Load resources from the topic's group
            const response = await getGroupResources(currentTopic);
            generateResources = response.resources;
        } catch (e) {
            console.error('Failed to load resources:', e);
            generateResources = [];
        } finally {
            resourcesLoading = false;
        }
    }

    async function openGenerateModal() {
        showGenerateModal = true;
        await loadGenerateResources();
    }

    function handleResourceRefresh() {
        loadGenerateResources();
    }

    function handleResourceError(event: CustomEvent<string>) {
        error = event.detail;
    }

    async function handleGenerateContent() {
        if (!generateQuery.trim()) return;

        try {
            isGenerating = true;
            error = '';
            await generateContent(currentTopic, generateQuery);
            await loadArticles();
            showGenerateModal = false;
            generateQuery = '';
            generateResources = [];
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to generate content';
        } finally {
            isGenerating = false;
        }
    }

    function formatDate(dateString: string) {
        return new Date(dateString).toLocaleString();
    }

    function truncateContent(content: string, maxLength: number = 200) {
        return content.length > maxLength ? content.substring(0, maxLength) + '...' : content;
    }

    async function handleDownloadPDF(articleId: number) {
        try {
            error = '';
            await downloadArticlePDF(articleId);
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to download PDF';
        }
    }

    // Load articles when topic changes
    $: if (currentTopic) {
        loadArticles();
    }

    onMount(() => {
        if (!$auth.isAuthenticated) {
            goto('/');
        }
    });
</script>

<div class="content-container">
    <!-- Topic Tabs with Generate Button -->
    <div class="tabs-container">
        <nav class="topic-tabs">
            {#each accessibleTopics as topic}
                <button
                    class="tab"
                    class:active={currentTopic === topic.id}
                    on:click={() => switchTopic(topic.id)}
                >
                    {topic.label}
                </button>
            {/each}
        </nav>
        <button class="generate-btn" on:click={openGenerateModal}>
            + Generate Content
        </button>
    </div>

    {#if error}
        <div class="error-message">{error}</div>
    {/if}

    {#if loading}
        <div class="loading">Loading articles...</div>
    {:else if articles.length === 0}
        <div class="empty-state">
            <h2>No Articles Yet</h2>
            <p>Create your first {topicLabels[currentTopic]} article using the "Generate Content" button above.</p>
        </div>
    {:else}
        <div class="articles-grid">
            {#each articles as article}
                <div class="article-card" class:inactive={!article.is_active}>
                    <div class="article-header">
                        <h3>{article.headline}</h3>
                        <div class="badges">
                            <span class="status-badge status-{article.status}">
                                {article.status}
                            </span>
                            {#if !article.is_active}
                                <span class="inactive-badge">Inactive</span>
                            {/if}
                        </div>
                    </div>

                    <div class="article-meta">
                        <span class="meta-item">
                            <strong>ID:</strong> {article.id}
                        </span>
                        <span class="meta-item">
                            <strong>Created:</strong> {formatDate(article.created_at)}
                        </span>
                    </div>

                    <div class="article-stats">
                        <div class="stat">
                            <span class="stat-label">Readership</span>
                            <span class="stat-value">{article.readership_count}</span>
                        </div>
                        <div class="stat">
                            <span class="stat-label">Rating</span>
                            <span class="stat-value">
                                {#if article.rating !== null}
                                    {article.rating}/5 ({article.rating_count})
                                {:else}
                                    Not rated
                                {/if}
                            </span>
                        </div>
                    </div>

                    {#if article.keywords}
                        <div class="keywords">
                            <strong>Keywords:</strong> {article.keywords}
                        </div>
                    {/if}

                    <div class="article-preview">
                        {truncateContent(article.content)}
                    </div>

                    <div class="article-actions">
                        <button
                            class="view-btn"
                            on:click={() => selectedArticle = article}
                        >
                            View
                        </button>
                        <button
                            class="edit-btn"
                            on:click={() => navigateToEditor(article.id)}
                            disabled={!article.is_active}
                        >
                            Edit
                        </button>
                        <button
                            class="submit-btn"
                            on:click={() => handleSubmitArticle(article.id)}
                            disabled={!article.is_active}
                        >Submit</button>
                        {#if $auth.user?.scopes?.includes('global:admin')}
                            {#if article.is_active}
                                <button
                                    class="delete-btn"
                                    on:click={() => handleDeleteArticle(article.id)}
                                >
                                    Delete
                                </button>
                            {:else}
                                <button
                                    class="reactivate-btn"
                                    on:click={() => handleReactivateArticle(article.id)}
                                >
                                    Reactivate
                                </button>
                            {/if}
                        {/if}
                    </div>
                </div>
            {/each}
        </div>
    {/if}
</div>

<!-- View Article Modal -->
{#if selectedArticle}
    <div class="modal-overlay" on:click={() => selectedArticle = null}>
        <div class="modal large" on:click|stopPropagation>
            <div class="modal-header">
                <h2>{selectedArticle.headline}</h2>
                <button class="close-btn" on:click={() => selectedArticle = null}>×</button>
            </div>

            <div class="modal-meta">
                <span><strong>ID:</strong> {selectedArticle.id}</span>
                <span><strong>Created:</strong> {formatDate(selectedArticle.created_at)}</span>
                <span><strong>Readership:</strong> {selectedArticle.readership_count}</span>
                <span>
                    <strong>Rating:</strong>
                    {#if selectedArticle.rating !== null}
                        {selectedArticle.rating}/5 ({selectedArticle.rating_count} ratings)
                    {:else}
                        Not rated
                    {/if}
                </span>
            </div>

            {#if selectedArticle.keywords}
                <div class="modal-keywords">
                    <strong>Keywords:</strong> {selectedArticle.keywords}
                </div>
            {/if}

            <div class="modal-content">
                <Markdown content={selectedArticle.content} />
            </div>

            <div class="modal-actions">
                <button class="download-pdf-btn" on:click={() => handleDownloadPDF(selectedArticle.id)}>
                    Download PDF
                </button>
                <button class="edit-modal-btn" on:click={() => navigateToEditor(selectedArticle.id)}>
                    Edit
                </button>
                <button class="submit-btn" on:click={() => { handleSubmitArticle(selectedArticle.id); selectedArticle = null; }}>Submit</button>
                <button on:click={() => selectedArticle = null}>Close</button>
            </div>
        </div>
    </div>
{/if}

<!-- Generate Content Modal -->
{#if showGenerateModal}
    <div class="modal-overlay" on:click={() => { showGenerateModal = false; generateQuery = ''; generateResources = []; }}>
        <div class="modal generate-modal" on:click|stopPropagation>
            <div class="modal-header">
                <h3>Generate New {topicLabels[currentTopic]} Content</h3>
                <button class="close-btn" on:click={() => { showGenerateModal = false; generateQuery = ''; generateResources = []; }}>×</button>
            </div>

            <div class="generate-modal-body">
                <p class="modal-description">
                    Use the content agent to research and create a new article.
                    You can add resources that will be used as context for generation.
                </p>

                <div class="form-group">
                    <label for="generate-query">Topic / Question</label>
                    <textarea
                        id="generate-query"
                        bind:value={generateQuery}
                        placeholder="Example: Impact of rising interest rates on tech stocks"
                        rows="3"
                        disabled={isGenerating}
                    ></textarea>
                </div>

                <!-- Resources Section -->
                <div class="resources-section">
                    <h4>Resources</h4>
                    <p class="resources-hint">Upload or paste resources to use as context for content generation. These will be added to the {currentTopic} shared resources.</p>
                    <ResourceEditor
                        resources={generateResources}
                        groupName="{currentTopic}:admin"
                        loading={resourcesLoading}
                        showDeleteButton={true}
                        showUnlinkButton={false}
                        on:refresh={handleResourceRefresh}
                        on:error={handleResourceError}
                    />
                </div>

                {#if isGenerating}
                    <div class="generating-indicator">
                        <div class="spinner"></div>
                        <p>Researching and generating content... This may take a minute.</p>
                    </div>
                {/if}
            </div>

            <div class="modal-actions">
                <button on:click={handleGenerateContent} disabled={!generateQuery.trim() || isGenerating}>
                    {isGenerating ? 'Generating...' : 'Generate Article'}
                </button>
                <button on:click={() => { showGenerateModal = false; generateQuery = ''; generateResources = []; }} disabled={isGenerating}>
                    Cancel
                </button>
            </div>
        </div>
    </div>
{/if}

<style>
    :global(body) {
        background: #fafafa;
    }

    .content-container {
        max-width: 1200px;
        margin: 0 auto;
        background: white;
        min-height: 100vh;
    }

    header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 2rem;
        padding-bottom: 1.5rem;
        border-bottom: 1px solid #e0e0e0;
        gap: 1rem;
        background: transparent;
    }

    .header-actions {
        display: flex;
        gap: 1rem;
        align-items: center;
    }

    /* Topic Tabs Container */
    .tabs-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: white;
        border-bottom: 1px solid #e5e7eb;
        margin-bottom: 2rem;
    }

    .topic-tabs {
        display: flex;
    }

    .tab {
        padding: 1rem 1.5rem;
        background: none;
        border: none;
        border-bottom: 2px solid transparent;
        cursor: pointer;
        font-size: 0.875rem;
        font-weight: 500;
        color: #6b7280;
        transition: all 0.2s;
    }

    .tab:hover {
        color: #1a1a1a;
        background: #f9fafb;
    }

    .tab.active {
        color: #3b82f6;
        border-bottom-color: #3b82f6;
    }

    header h1 {
        margin: 0 0 0.5rem 0;
        color: #1a1a1a;
        font-size: 1.75rem;
        font-weight: 600;
        letter-spacing: -0.01em;
    }

    .subtitle {
        margin: 0;
        color: #6b7280;
        font-size: 0.95rem;
        font-weight: 400;
    }

    .back-link {
        color: #6b7280;
        text-decoration: none;
        font-weight: 500;
        padding: 0.5rem 1rem;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        transition: all 0.2s;
        font-size: 0.875rem;
    }

    .back-link:hover {
        background: #f9fafb;
        border-color: #d1d5db;
        color: #1a1a1a;
    }

    .generate-btn {
        padding: 0.625rem 1.25rem;
        background: #3b82f6;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-weight: 500;
        font-size: 0.875rem;
        transition: all 0.2s;
    }

    .generate-btn:hover {
        background: #2563eb;
    }

    .error-message {
        background: #ffebee;
        color: #d32f2f;
        padding: 1rem;
        border-radius: 4px;
        margin-bottom: 1rem;
    }

    .loading {
        text-align: center;
        padding: 3rem;
        color: #666;
    }

    .empty-state {
        text-align: center;
        padding: 4rem 2rem;
        margin: 0 2rem 2rem 2rem;
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
    }

    .empty-state h2 {
        color: #1a1a1a;
        margin-bottom: 1rem;
        font-weight: 600;
    }

    .empty-state p {
        color: #6b7280;
        font-size: 1rem;
    }

    .articles-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
        gap: 1rem;
        padding: 0 2rem 2rem 2rem;
    }

    .article-card {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        padding: 1.5rem;
        transition: all 0.2s;
    }

    .article-card:hover {
        border-color: #3b82f6;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
    }

    .article-card.inactive {
        opacity: 0.6;
        background: #f5f5f5;
    }

    .article-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 1rem;
        margin-bottom: 1rem;
    }

    .article-header h3 {
        margin: 0;
        color: #333;
        font-size: 1.1rem;
        line-height: 1.4;
        flex: 1;
    }

    .badges {
        display: flex;
        gap: 0.5rem;
        align-items: center;
    }

    .status-badge {
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 500;
        white-space: nowrap;
        text-transform: capitalize;
    }

    .status-badge.status-draft {
        background: #9e9e9e;
        color: white;
    }

    .status-badge.status-editor {
        background: #ff9800;
        color: white;
    }

    .status-badge.status-published {
        background: #4caf50;
        color: white;
    }

    .inactive-badge {
        padding: 0.25rem 0.5rem;
        background: #f44336;
        color: white;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 500;
        white-space: nowrap;
    }

    .article-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 1rem;
        margin-bottom: 1rem;
        font-size: 0.85rem;
        color: #666;
    }

    .meta-item {
        display: flex;
        gap: 0.25rem;
    }

    .article-stats {
        display: flex;
        gap: 2rem;
        margin-bottom: 1rem;
        padding: 0.75rem;
        background: #f9f9f9;
        border-radius: 4px;
    }

    .stat {
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
    }

    .stat-label {
        font-size: 0.75rem;
        color: #666;
        text-transform: uppercase;
        font-weight: 600;
    }

    .stat-value {
        font-size: 1rem;
        color: #333;
        font-weight: 500;
    }

    .keywords {
        margin-bottom: 1rem;
        font-size: 0.85rem;
        color: #666;
        line-height: 1.5;
    }

    .article-preview {
        margin-bottom: 1rem;
        padding: 0.75rem;
        background: #fafafa;
        border-left: 3px solid #3b82f6;
        font-size: 0.9rem;
        line-height: 1.6;
        color: #555;
    }

    .article-actions {
        display: flex;
        gap: 0.5rem;
    }

    .article-actions button {
        flex: 1;
        padding: 0.5rem 1rem;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.875rem;
        font-weight: 500;
        transition: all 0.2s;
    }

    .view-btn {
        background: #f9fafb;
        color: #374151;
        border: 1px solid #e5e7eb;
    }

    .view-btn:hover {
        background: #f3f4f6;
        border-color: #d1d5db;
    }

    .edit-btn {
        background: #3b82f6;
        color: white;
    }

    .edit-btn:hover {
        background: #2563eb;
    }

    .submit-btn {
        background: #10b981;
        color: white;
    }

    .submit-btn:hover:not(:disabled) {
        background: #059669;
    }

    .edit-btn:disabled,
    .submit-btn:disabled {
        background: #d1d5db;
        cursor: not-allowed;
    }

    .rate-btn {
        background: #f9fafb;
        color: #374151;
        border: 1px solid #e5e7eb;
    }

    .rate-btn:hover {
        background: #f3f4f6;
        border-color: #d1d5db;
    }

    .delete-btn {
        background: #ef4444;
        color: white;
    }

    .delete-btn:hover:not(:disabled) {
        background: #dc2626;
    }

    .delete-btn:disabled {
        background: #d1d5db;
        cursor: not-allowed;
    }

    .reactivate-btn {
        background: #8b5cf6;
        color: white;
    }

    .reactivate-btn:hover {
        background: #7c3aed;
    }

    /* Modal Styles */
    .modal-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.5);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 1000;
        padding: 2rem;
    }

    .modal {
        background: white;
        padding: 2rem;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);
        min-width: 400px;
        max-width: 500px;
        max-height: 90vh;
        overflow-y: auto;
    }

    .modal.large {
        min-width: 600px;
        max-width: 900px;
    }

    .modal.generate-modal {
        min-width: 600px;
        max-width: 800px;
    }

    .generate-modal-body {
        padding: 1.5rem 2rem;
        max-height: 70vh;
        overflow-y: auto;
    }

    .resources-section {
        margin-top: 1.5rem;
        padding-top: 1.5rem;
        border-top: 1px solid #e5e7eb;
    }

    .resources-section h4 {
        margin: 0 0 0.5rem 0;
        font-size: 1rem;
        color: #374151;
    }

    .resources-hint {
        margin: 0 0 1rem 0;
        font-size: 0.85rem;
        color: #6b7280;
    }

    .modal-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 1rem;
        margin-bottom: 1rem;
        padding-bottom: 1rem;
        border-bottom: 2px solid #e0e0e0;
    }

    .modal-header h2 {
        margin: 0;
        color: #333;
        flex: 1;
    }

    .close-btn {
        background: none;
        border: none;
        font-size: 2rem;
        line-height: 1;
        cursor: pointer;
        color: #666;
        padding: 0;
        width: 32px;
        height: 32px;
    }

    .close-btn:hover {
        color: #333;
    }

    .modal-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 1rem;
        margin-bottom: 1rem;
        padding: 1rem;
        background: #f9f9f9;
        border-radius: 4px;
        font-size: 0.85rem;
    }

    .modal-keywords {
        margin-bottom: 1rem;
        padding: 0.75rem;
        background: #e3f2fd;
        border-radius: 4px;
        font-size: 0.85rem;
    }

    .modal-content {
        margin-bottom: 1.5rem;
        line-height: 1.8;
        max-height: 50vh;
        overflow-y: auto;
        padding: 1rem;
        border: 1px solid #e0e0e0;
        border-radius: 4px;
    }

    .modal h3 {
        margin-top: 0;
        color: #333;
    }

    .article-title {
        color: #666;
        font-style: italic;
        margin-bottom: 1.5rem;
    }

    .rating-selector {
        display: flex;
        gap: 0.5rem;
        justify-content: center;
        margin: 1.5rem 0;
    }

    .rating-btn {
        background: #f9fafb;
        border: 1px solid #e5e7eb;
        font-size: 1rem;
        cursor: pointer;
        padding: 0.75rem 1rem;
        border-radius: 4px;
        transition: all 0.2s;
        color: #6b7280;
        font-weight: 500;
        min-width: 48px;
    }

    .rating-btn:hover {
        background: #f3f4f6;
        border-color: #d1d5db;
    }

    .rating-btn.selected {
        background: #3b82f6;
        border-color: #3b82f6;
        color: white;
    }

    .rating-text {
        text-align: center;
        font-weight: 500;
        color: #374151;
        margin-bottom: 1.5rem;
        font-size: 0.95rem;
    }

    .modal-actions {
        display: flex;
        gap: 1rem;
        justify-content: flex-end;
    }

    .modal-actions button {
        padding: 0.75rem 1.5rem;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-weight: 500;
    }

    .modal-actions button:first-child,
    .edit-modal-btn,
    .download-pdf-btn {
        background: #3b82f6;
        color: white;
    }

    .modal-actions button:first-child:hover:not(:disabled),
    .edit-modal-btn:hover,
    .download-pdf-btn:hover {
        background: #006399;
    }

    .download-pdf-btn {
        background: #10b981;
    }

    .download-pdf-btn:hover {
        background: #059669;
    }

    .modal-actions button:first-child:disabled {
        background: #ccc;
        cursor: not-allowed;
    }

    .modal-actions button:last-child:not(.edit-modal-btn) {
        background: #f5f5f5;
        color: #333;
    }

    .modal-actions button:last-child:hover {
        background: #e0e0e0;
    }

    .form-group {
        margin-bottom: 1.5rem;
    }

    .form-group label {
        display: block;
        margin-bottom: 0.5rem;
        font-weight: 600;
        color: #333;
    }

    .form-group textarea {
        width: 100%;
        padding: 0.75rem;
        border: 1px solid #e0e0e0;
        border-radius: 4px;
        font-size: 1rem;
        font-family: inherit;
        resize: vertical;
        min-height: 100px;
        line-height: 1.6;
    }

    .modal-description {
        color: #666;
        margin-bottom: 1.5rem;
        line-height: 1.6;
    }

    .generating-indicator {
        text-align: center;
        padding: 2rem;
        background: #f9f9f9;
        border-radius: 4px;
        margin-bottom: 1.5rem;
    }

    .spinner {
        width: 40px;
        height: 40px;
        margin: 0 auto 1rem;
        border: 4px solid #f3f3f3;
        border-top: 4px solid #3b82f6;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    .generating-indicator p {
        color: #666;
        margin: 0;
    }
</style>
