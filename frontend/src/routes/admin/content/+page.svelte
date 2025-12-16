<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { getAdminArticles, deleteArticle, rateArticle, editArticle, generateContent, downloadArticlePDF } from '$lib/api';
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import Markdown from '$lib/components/Markdown.svelte';

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
        created_at: string;
        updated_at: string;
        created_by_agent: string;
        is_active: boolean;
    }

    let currentTopic: Topic = 'macro';
    let articles: Article[] = [];
    let loading = true;
    let error = '';
    let selectedArticle: Article | null = null;
    let showRatingModal = false;
    let userRating: number = 0;
    let showGenerateModal = false;
    let generateQuery = '';
    let isGenerating = false;

    const topics = [
        { id: 'macro' as Topic, label: 'Macro' },
        { id: 'equity' as Topic, label: 'Equities' },
        { id: 'fixed_income' as Topic, label: 'Fixed Income' },
        { id: 'esg' as Topic, label: 'ESG' }
    ];

    // Check if user is admin or analyst
    $: if (!$auth.isAuthenticated) {
        goto('/');
    }

    // Check if user can edit content for the current topic
    function canEditTopic(topic: string): boolean {
        if (!$auth.user?.scopes) return false;

        // Admin can edit all
        if ($auth.user.scopes.includes('admin')) return true;

        // Check for specific analyst permission
        const topicMap: Record<string, string> = {
            'macro': 'macro_analyst',
            'equity': 'equity_analyst',
            'fixed_income': 'fi_analyst',
            'esg': 'esg_analyst'
        };

        return $auth.user.scopes.includes(topicMap[topic]);
    }

    async function loadArticles() {
        try {
            loading = true;
            error = '';
            articles = await getAdminArticles(currentTopic);
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

    async function handleRateArticle() {
        if (!selectedArticle || !userRating) return;

        try {
            error = '';
            await rateArticle(selectedArticle.id, userRating);
            await loadArticles();
            selectedArticle = null;
            showRatingModal = false;
            userRating = 0;
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to rate article';
        }
    }

    function openRatingModal(article: Article) {
        selectedArticle = article;
        showRatingModal = true;
        userRating = 0;
    }

    function switchTopic(topic: Topic) {
        currentTopic = topic;
        loadArticles();
    }

    function navigateToEditor(articleId: number) {
        goto(`/admin/content/edit/${articleId}`);
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

    onMount(() => {
        loadArticles();
    });
</script>

<div class="admin-content-container">
    <header>
        <div>
            <h1>Content Management</h1>
            <p class="subtitle">Inspect, rate, edit, and generate research articles</p>
        </div>
        <div class="header-actions">
            {#if canEditTopic(currentTopic)}
                <button class="generate-btn" on:click={() => showGenerateModal = true}>
                    + Generate Content
                </button>
            {/if}
            <a href="/admin" class="back-link">Back to Admin</a>
        </div>
    </header>

    {#if error}
        <div class="error-message">{error}</div>
    {/if}

    <nav class="topic-tabs">
        {#each topics as topic}
            <button
                class="tab"
                class:active={currentTopic === topic.id}
                on:click={() => switchTopic(topic.id)}
            >
                {topic.label}
            </button>
        {/each}
    </nav>

    {#if loading}
        <div class="loading">Loading articles...</div>
    {:else if articles.length === 0}
        <div class="empty-state">
            <p>No articles found for {currentTopic}</p>
        </div>
    {:else}
        <div class="articles-grid">
            {#each articles as article}
                <div class="article-card" class:inactive={!article.is_active}>
                    <div class="article-header">
                        <h3>{article.headline}</h3>
                        {#if !article.is_active}
                            <span class="inactive-badge">Inactive</span>
                        {/if}
                    </div>

                    <div class="article-meta">
                        <span class="meta-item">
                            <strong>ID:</strong> {article.id}
                        </span>
                        <span class="meta-item">
                            <strong>Agent:</strong> {article.created_by_agent}
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
                                    {'⭐'.repeat(article.rating)} ({article.rating_count})
                                {:else}
                                    No ratings
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
                            on:click={() => { selectedArticle = article; showRatingModal = false; }}
                        >
                            View Full
                        </button>
                        {#if canEditTopic(article.topic)}
                            <button
                                class="edit-btn"
                                on:click={() => navigateToEditor(article.id)}
                            >
                                Edit
                            </button>
                        {/if}
                        <button
                            class="rate-btn"
                            on:click={() => openRatingModal(article)}
                        >
                            Rate
                        </button>
                        {#if $auth.user?.scopes?.includes('admin')}
                            <button
                                class="delete-btn"
                                on:click={() => handleDeleteArticle(article.id)}
                                disabled={!article.is_active}
                            >
                                Delete
                            </button>
                        {/if}
                    </div>
                </div>
            {/each}
        </div>
    {/if}
</div>

<!-- View Article Modal -->
{#if selectedArticle && !showRatingModal}
    <div class="modal-overlay" on:click={() => selectedArticle = null}>
        <div class="modal large" on:click|stopPropagation>
            <div class="modal-header">
                <h2>{selectedArticle.headline}</h2>
                <button class="close-btn" on:click={() => selectedArticle = null}>×</button>
            </div>

            <div class="modal-meta">
                <span><strong>ID:</strong> {selectedArticle.id}</span>
                <span><strong>Agent:</strong> {selectedArticle.created_by_agent}</span>
                <span><strong>Created:</strong> {formatDate(selectedArticle.created_at)}</span>
                <span><strong>Readership:</strong> {selectedArticle.readership_count}</span>
                <span>
                    <strong>Rating:</strong>
                    {#if selectedArticle.rating !== null}
                        {'⭐'.repeat(selectedArticle.rating)} ({selectedArticle.rating_count} ratings)
                    {:else}
                        No ratings
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
                <button on:click={() => selectedArticle = null}>Close</button>
            </div>
        </div>
    </div>
{/if}

<!-- Rate Article Modal -->
{#if selectedArticle && showRatingModal}
    <div class="modal-overlay" on:click={() => { selectedArticle = null; showRatingModal = false; userRating = 0; }}>
        <div class="modal" on:click|stopPropagation>
            <h3>Rate Article</h3>
            <p class="article-title">{selectedArticle.headline}</p>

            <div class="rating-selector">
                {#each [1, 2, 3, 4, 5] as star}
                    <button
                        class="star-btn"
                        class:selected={userRating >= star}
                        on:click={() => userRating = star}
                    >
                        ⭐
                    </button>
                {/each}
            </div>

            {#if userRating > 0}
                <p class="rating-text">{userRating} star{userRating > 1 ? 's' : ''}</p>
            {/if}

            <div class="modal-actions">
                <button on:click={handleRateArticle} disabled={!userRating}>
                    Submit Rating
                </button>
                <button on:click={() => { selectedArticle = null; showRatingModal = false; userRating = 0; }}>
                    Cancel
                </button>
            </div>
        </div>
    </div>
{/if}

<!-- Generate Content Modal -->
{#if showGenerateModal}
    <div class="modal-overlay" on:click={() => { showGenerateModal = false; generateQuery = ''; }}>
        <div class="modal" on:click|stopPropagation>
            <h3>Generate New {topics.find(t => t.id === currentTopic)?.label} Content</h3>
            <p class="modal-description">
                Use the content agent to research and create a new article.
                Enter a topic or question below.
            </p>

            <div class="form-group">
                <label for="generate-query">Topic / Question</label>
                <textarea
                    id="generate-query"
                    bind:value={generateQuery}
                    placeholder="Example: Impact of rising interest rates on tech stocks"
                    rows="4"
                    disabled={isGenerating}
                ></textarea>
            </div>

            {#if isGenerating}
                <div class="generating-indicator">
                    <div class="spinner"></div>
                    <p>Researching and generating content... This may take a minute.</p>
                </div>
            {/if}

            <div class="modal-actions">
                <button on:click={handleGenerateContent} disabled={!generateQuery.trim() || isGenerating}>
                    {isGenerating ? 'Generating...' : 'Generate Article'}
                </button>
                <button on:click={() => { showGenerateModal = false; generateQuery = ''; }} disabled={isGenerating}>
                    Cancel
                </button>
            </div>
        </div>
    </div>
{/if}

<style>
    .admin-content-container {
        max-width: 1400px;
        margin: 0 auto;
        padding: 2rem;
    }

    header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 2rem;
        gap: 1rem;
    }

    .header-actions {
        display: flex;
        gap: 1rem;
        align-items: center;
    }

    header h1 {
        margin: 0 0 0.5rem 0;
        color: #333;
    }

    .subtitle {
        margin: 0;
        color: #666;
        font-size: 0.9rem;
    }

    .back-link {
        color: #0077b5;
        text-decoration: none;
        font-weight: 500;
    }

    .back-link:hover {
        text-decoration: underline;
    }

    .error-message {
        background: #ffebee;
        color: #d32f2f;
        padding: 1rem;
        border-radius: 4px;
        margin-bottom: 1rem;
    }

    .loading, .empty-state {
        text-align: center;
        padding: 3rem;
        color: #666;
    }

    .topic-tabs {
        display: flex;
        gap: 0.5rem;
        margin-bottom: 2rem;
        border-bottom: 2px solid #e0e0e0;
    }

    .tab {
        padding: 0.75rem 1.5rem;
        background: none;
        border: none;
        border-bottom: 3px solid transparent;
        cursor: pointer;
        font-size: 1rem;
        font-weight: 500;
        color: #666;
        transition: all 0.2s;
    }

    .tab:hover {
        color: #0077b5;
    }

    .tab.active {
        color: #0077b5;
        border-bottom-color: #0077b5;
    }

    .articles-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
        gap: 1.5rem;
    }

    .article-card {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 1.5rem;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        transition: box-shadow 0.2s;
    }

    .article-card:hover {
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
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

    .inactive-badge {
        padding: 0.25rem 0.5rem;
        background: #ff9800;
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
        border-left: 3px solid #0077b5;
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
        background: #0077b5;
        color: white;
    }

    .view-btn:hover {
        background: #006399;
    }

    .rate-btn {
        background: #4caf50;
        color: white;
    }

    .rate-btn:hover {
        background: #45a049;
    }

    .edit-btn {
        background: #ff9800;
        color: white;
    }

    .edit-btn:hover {
        background: #f57c00;
    }

    .generate-btn {
        padding: 0.75rem 1.5rem;
        background: #4caf50;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-weight: 500;
        font-size: 0.9rem;
        transition: all 0.2s;
    }

    .generate-btn:hover {
        background: #45a049;
    }

    .delete-btn {
        background: #f44336;
        color: white;
    }

    .delete-btn:hover:not(:disabled) {
        background: #d32f2f;
    }

    .delete-btn:disabled {
        background: #ccc;
        cursor: not-allowed;
    }

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

    .star-btn {
        background: none;
        border: none;
        font-size: 2rem;
        cursor: pointer;
        opacity: 0.3;
        transition: all 0.2s;
        padding: 0.25rem;
    }

    .star-btn:hover,
    .star-btn.selected {
        opacity: 1;
        transform: scale(1.1);
    }

    .rating-text {
        text-align: center;
        font-weight: 600;
        color: #0077b5;
        margin-bottom: 1.5rem;
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

    .modal-actions button:first-child {
        background: #0077b5;
        color: white;
    }

    .modal-actions button:first-child:hover:not(:disabled) {
        background: #006399;
    }

    .modal-actions button:first-child:disabled {
        background: #ccc;
        cursor: not-allowed;
    }

    .download-pdf-btn {
        background: #10b981;
        color: white;
    }

    .download-pdf-btn:hover {
        background: #059669;
    }

    .modal-actions button:last-child {
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
        border-top: 4px solid #0077b5;
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
