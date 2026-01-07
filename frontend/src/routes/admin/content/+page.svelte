<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { getAdminArticles, deleteArticle, reactivateArticle, editArticle, generateContent, searchArticles, type SearchParams } from '$lib/api';
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import { navigationContext } from '$lib/stores/navigation';

    // Set navigation context for admin content section
    navigationContext.setContext({ section: 'admin', topic: null, subNav: 'content', articleId: null, articleHeadline: null, role: 'admin' });

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
        author?: string;
        editor?: string;
    }

    interface ExtendedSearchParams extends SearchParams {
        topic?: string;
    }

    let currentTopic: Topic = 'macro';
    let articles: Article[] = [];
    let loading = true;
    let error = '';
    let showGenerateModal = false;
    let generateQuery = '';
    let isGenerating = false;

    // Search state
    let showSearchSection = false;
    let searchParams: ExtendedSearchParams = {
        topic: 'all',  // Default to 'all' topics
        limit: 10
    };
    let isSearching = false;
    let searchActive = false;

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

        // Global admin can edit all
        if ($auth.user.scopes.includes('global:admin')) return true;

        // Check for topic-specific admin, analyst, or editor role
        return $auth.user.scopes.includes(`${topic}:admin`) ||
               $auth.user.scopes.includes(`${topic}:analyst`) ||
               $auth.user.scopes.includes(`${topic}:editor`);
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
            await deleteArticle(currentTopic, articleId);
            await loadArticles();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to delete article';
        }
    }

    async function handleReactivateArticle(articleId: number) {
        if (!confirm('Are you sure you want to reactivate this article?')) return;

        try {
            error = '';
            await reactivateArticle(currentTopic, articleId);
            await loadArticles();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to reactivate article';
        }
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

    async function handleSearch() {
        try {
            isSearching = true;
            error = '';
            const searchTopic = searchParams.topic || 'all';
            articles = await searchArticles(searchTopic, searchParams);
            searchActive = true;
        } catch (e) {
            error = e instanceof Error ? e.message : 'Search failed';
            console.error('Search error:', e);
        } finally {
            isSearching = false;
        }
    }

    function handleClearSearch() {
        searchParams = { topic: 'all', limit: 10 };
        searchActive = false;
        loadArticles();
    }

    function formatDate(dateString: string) {
        return new Date(dateString).toLocaleString();
    }

    function truncateContent(content: string, maxLength: number = 200) {
        return content.length > maxLength ? content.substring(0, maxLength) + '...' : content;
    }

    onMount(() => {
        loadArticles();
    });
</script>

<div class="admin-content-container">
    {#if error}
        <div class="error-message">{error}</div>
    {/if}

    <!-- Tabs with Generate Button -->
    <div class="tabs-container">
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
        {#if canEditTopic(currentTopic)}
            <button class="generate-btn" on:click={() => showGenerateModal = true}>
                + Generate Content
            </button>
        {/if}
    </div>

    <!-- Search Section -->
    <div class="search-section">
        <button class="toggle-search-btn" on:click={() => showSearchSection = !showSearchSection}>
            {showSearchSection ? '▼' : '▶'} Advanced Search
        </button>

        {#if showSearchSection}
            <div class="search-form">
                <div class="search-grid">
                    <div class="search-field">
                        <label for="search-topic">Topic</label>
                        <select
                            id="search-topic"
                            bind:value={searchParams.topic}
                        >
                            <option value="all">All Topics</option>
                            <option value="macro">Macro</option>
                            <option value="equity">Equities</option>
                            <option value="fixed_income">Fixed Income</option>
                            <option value="esg">ESG</option>
                        </select>
                    </div>

                    <div class="search-field">
                        <label for="search-query">General Search (Vector + Keyword)</label>
                        <input
                            id="search-query"
                            type="text"
                            bind:value={searchParams.q}
                            placeholder="Search in headline, keywords, and content..."
                        />
                    </div>

                    <div class="search-field">
                        <label for="search-headline">Headline</label>
                        <input
                            id="search-headline"
                            type="text"
                            bind:value={searchParams.headline}
                            placeholder="Filter by headline..."
                        />
                    </div>

                    <div class="search-field">
                        <label for="search-keywords">Keywords</label>
                        <input
                            id="search-keywords"
                            type="text"
                            bind:value={searchParams.keywords}
                            placeholder="Filter by keywords..."
                        />
                    </div>

                    <div class="search-field">
                        <label for="search-author">Author</label>
                        <input
                            id="search-author"
                            type="text"
                            bind:value={searchParams.author}
                            placeholder="Filter by author..."
                        />
                    </div>

                    <div class="search-field">
                        <label for="search-created-after">Created After</label>
                        <input
                            id="search-created-after"
                            type="date"
                            bind:value={searchParams.created_after}
                        />
                    </div>

                    <div class="search-field">
                        <label for="search-created-before">Created Before</label>
                        <input
                            id="search-created-before"
                            type="date"
                            bind:value={searchParams.created_before}
                        />
                    </div>

                    <div class="search-field">
                        <label for="search-limit">Results Limit</label>
                        <input
                            id="search-limit"
                            type="number"
                            bind:value={searchParams.limit}
                            min="1"
                            max="50"
                        />
                    </div>
                </div>

                <div class="search-actions">
                    <button class="search-btn" on:click={handleSearch} disabled={isSearching}>
                        {isSearching ? 'Searching...' : 'Search'}
                    </button>
                    <button class="clear-btn" on:click={handleClearSearch} disabled={isSearching}>
                        Clear & Show All
                    </button>
                </div>

                {#if searchActive}
                    <div class="search-status">
                        Showing search results ({articles.length} found)
                    </div>
                {/if}
            </div>
        {/if}
    </div>

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
                        {#if canEditTopic(article.topic)}
                            <button
                                class="edit-btn"
                                on:click={() => navigateToEditor(article.id)}
                            >
                                Edit
                            </button>
                        {/if}
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
    :global(body) {
        background: #fafafa;
    }

    .admin-content-container {
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
        color: #3b82f6;
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

    /* Search Section Styles */
    .search-section {
        background: #f5f5f5;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 1.5rem;
    }

    .toggle-search-btn {
        background: none;
        border: none;
        color: #3b82f6;
        font-size: 1rem;
        font-weight: 600;
        cursor: pointer;
        padding: 0.5rem;
        width: 100%;
        text-align: left;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .toggle-search-btn:hover {
        color: #005a8c;
    }

    .search-form {
        margin-top: 1rem;
        padding-top: 1rem;
        border-top: 1px solid #ddd;
    }

    .search-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 1rem;
        margin-bottom: 1rem;
    }

    .search-field {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
    }

    .search-field label {
        font-size: 0.875rem;
        font-weight: 500;
        color: #333;
    }

    .search-field input,
    .search-field select {
        padding: 0.5rem;
        border: 1px solid #ccc;
        border-radius: 4px;
        font-size: 0.875rem;
    }

    .search-field input:focus,
    .search-field select:focus {
        outline: none;
        border-color: #3b82f6;
        box-shadow: 0 0 0 2px rgba(0, 119, 181, 0.1);
    }

    .search-field select {
        cursor: pointer;
        background-color: white;
    }

    .search-actions {
        display: flex;
        gap: 1rem;
        margin-top: 1rem;
    }

    .search-btn {
        background: #3b82f6;
        color: white;
        border: none;
        padding: 0.75rem 1.5rem;
        border-radius: 4px;
        font-weight: 600;
        cursor: pointer;
        transition: background 0.2s;
    }

    .search-btn:hover:not(:disabled) {
        background: #005a8c;
    }

    .search-btn:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }

    .clear-btn {
        background: #666;
        color: white;
        border: none;
        padding: 0.75rem 1.5rem;
        border-radius: 4px;
        font-weight: 600;
        cursor: pointer;
        transition: background 0.2s;
    }

    .clear-btn:hover:not(:disabled) {
        background: #444;
    }

    .clear-btn:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }

    .search-status {
        margin-top: 1rem;
        padding: 0.75rem;
        background: #e3f2fd;
        border-left: 4px solid #3b82f6;
        border-radius: 4px;
        color: #005a8c;
        font-weight: 500;
    }

    .loading, .empty-state {
        text-align: center;
        padding: 3rem;
        color: #666;
    }

    /* Tabs Container */
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
        background: #3b82f6;
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

    .reactivate-btn {
        background: #4caf50;
        color: white;
    }

    .reactivate-btn:hover {
        background: #45a049;
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
        display: flex;
        flex-direction: column;
        padding: 0;
        overflow: hidden;
    }

    /* Fixed Header and Actions */
    .modal-header-fixed {
        flex-shrink: 0;
        background: white;
        border-bottom: 1px solid #e0e0e0;
    }

    .modal-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 1rem;
        padding: 1.5rem 2rem 1rem 2rem;
        border-bottom: 2px solid #e0e0e0;
    }

    .modal-actions-fixed {
        display: flex;
        gap: 1rem;
        padding: 1rem 2rem;
        background: #f9fafb;
        border-bottom: 1px solid #e0e0e0;
    }

    .modal-actions-fixed button {
        padding: 0.75rem 1.5rem;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-weight: 500;
        font-size: 0.875rem;
        transition: all 0.2s;
    }

    .modal-actions-fixed button:first-child {
        background: #e5e7eb;
        color: #374151;
    }

    .modal-actions-fixed button:first-child:hover {
        background: #d1d5db;
    }

    .modal-actions-fixed .download-pdf-btn {
        background: #3b82f6;
        color: white;
    }

    .modal-actions-fixed .download-pdf-btn:hover {
        background: #2563eb;
    }

    .modal-actions-fixed .rate-btn {
        background: #4caf50;
        color: white;
    }

    .modal-actions-fixed .rate-btn:hover {
        background: #45a049;
    }

    /* Scrollable Content Area */
    .modal-content-scrollable {
        flex: 1;
        overflow-y: auto;
        padding: 2rem;
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
        margin-bottom: 1.5rem;
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
        line-height: 1.8;
        padding: 1rem;
        border: 1px solid #e0e0e0;
        border-radius: 4px;
        background: white;
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
        color: #3b82f6;
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
        background: #3b82f6;
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
