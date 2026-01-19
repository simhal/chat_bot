<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { getArticle, searchArticles, rateArticle, getEntitledTopics, getArticlePublicationResources, getPublishedArticleHtmlUrl, downloadArticlePDF, type Topic as TopicType, type ArticlePublicationResources } from '$lib/api';
    import Markdown from '$lib/components/Markdown.svelte';
    import { onMount, onDestroy } from 'svelte';
    import { browser } from '$app/environment';
    import { goto } from '$app/navigation';
    import { navigationContext } from '$lib/stores/navigation';
    import { actionStore, type UIAction, type ActionResult } from '$lib/stores/actions';

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
        author?: string;
        editor?: string;
        user_rating?: number | null;
    }

    let error = '';

    // Article detail state
    let selectedArticle: Article | null = null;
    let selectedArticleResources: ArticlePublicationResources | null = null;
    let showRatingModal = false;
    let userRating = 0;

    // Search state
    let searchResults: Article[] = [];
    let searchLoading = false;
    let searchParams = {
        topic: 'all' as string,
        q: '',
        headline: '',
        keywords: '',
        author: '',
        created_after: '',
        created_before: '',
        limit: 10
    };

    // Topics loaded from database
    let dbTopics: TopicType[] = [];
    let topicsLoading = false;
    let topicsLoadedForUser: string | null = null;

    async function loadTopicsFromDb() {
        if (topicsLoading) return;
        try {
            topicsLoading = true;
            dbTopics = await getEntitledTopics('reader');
            topicsLoadedForUser = $auth.user?.email || 'authenticated';
        } catch (e) {
            console.error('Error loading topics:', e);
            dbTopics = [];
            topicsLoadedForUser = null;
        } finally {
            topicsLoading = false;
        }
    }

    // Load topics when auth state changes
    $: {
        const currentUser = $auth.user?.email || ($auth.isAuthenticated ? 'authenticated' : null);
        if ($auth.isAuthenticated && currentUser !== topicsLoadedForUser && !topicsLoading) {
            loadTopicsFromDb();
        } else if (!$auth.isAuthenticated) {
            dbTopics = [];
            topicsLoadedForUser = null;
        }
    }

    // Redirect if not authenticated
    $: if (browser && !$auth.isAuthenticated) {
        goto('/');
    }

    function formatDate(dateString: string) {
        return new Date(dateString).toLocaleDateString();
    }

    async function handleArticleClick(article: Article) {
        // Navigate to article detail page
        goto(`/article/${article.id}`);
    }

    async function handleSearch() {
        try {
            searchLoading = true;
            error = '';

            const params: any = { limit: searchParams.limit };
            if (searchParams.q) params.q = searchParams.q;
            if (searchParams.headline) params.headline = searchParams.headline;
            if (searchParams.keywords) params.keywords = searchParams.keywords;
            if (searchParams.author) params.author = searchParams.author;
            if (searchParams.created_after) params.created_after = searchParams.created_after;
            if (searchParams.created_before) params.created_before = searchParams.created_before;

            searchResults = await searchArticles(searchParams.topic, params);
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to search articles';
            console.error('Error searching articles:', e);
        } finally {
            searchLoading = false;
        }
    }

    function handleClearSearch() {
        searchParams = {
            topic: 'all',
            q: '',
            headline: '',
            keywords: '',
            author: '',
            created_after: '',
            created_before: '',
            limit: 10
        };
        searchResults = [];
        error = '';
    }

    // Action handlers for chat-triggered UI actions
    let actionUnsubscribers: (() => void)[] = [];

    async function handleSearchArticlesAction(action: UIAction): Promise<ActionResult> {
        const query = action.params?.search_query;
        if (!query) {
            return { success: false, action: 'search_articles', error: 'No search query specified' };
        }
        searchParams.q = query;
        await handleSearch();
        return { success: true, action: 'search_articles', message: `Searching for: ${query}` };
    }

    async function handleClearSearchAction(action: UIAction): Promise<ActionResult> {
        handleClearSearch();
        return { success: true, action: 'clear_search', message: 'Search cleared' };
    }

    async function handleOpenArticleAction(action: UIAction): Promise<ActionResult> {
        const articleId = action.params?.article_id;
        if (!articleId) {
            return { success: false, action: 'open_article', error: 'No article ID specified' };
        }
        goto(`/article/${articleId}`);
        return { success: true, action: 'open_article', message: `Opening article #${articleId}` };
    }

    onMount(() => {
        // Set navigation context for reader_search section (from sections.json)
        navigationContext.setSection('reader_search' as any);

        // Register action handlers (from ui_actions.json: search_articles, clear_search, open_article)
        actionUnsubscribers.push(
            actionStore.registerHandler('search_articles', handleSearchArticlesAction),
            actionStore.registerHandler('clear_search', handleClearSearchAction),
            actionStore.registerHandler('open_article', handleOpenArticleAction)
        );
    });

    onDestroy(() => {
        actionUnsubscribers.forEach(unsub => unsub());
    });
</script>

<div class="search-container">
    {#if error}
        <div class="error-message">{error}</div>
    {/if}

    <!-- Search Form -->
    <div class="search-form" data-testid="advanced-search-panel">
        <h2>Advanced Article Search</h2>

        <div class="form-row">
            <div class="form-group">
                <label for="search-topic">Topic</label>
                <select id="search-topic" bind:value={searchParams.topic} data-testid="search-topic">
                    <option value="all">All Topics</option>
                    {#each dbTopics.filter(t => t.visible && t.active).sort((a, b) => a.sort_order - b.sort_order) as topic}
                        <option value={topic.slug}>{topic.title}</option>
                    {/each}
                </select>
            </div>

            <div class="form-group">
                <label for="search-limit">Results Limit</label>
                <input
                    id="search-limit"
                    type="number"
                    bind:value={searchParams.limit}
                    min="1"
                    max="50"
                    placeholder="10"
                />
            </div>
        </div>

        <div class="form-group">
            <label for="search-query">General Search (Vector & Keyword)</label>
            <input
                id="search-query"
                type="text"
                bind:value={searchParams.q}
                placeholder="Search across content, headline, and keywords..."
                data-testid="search-input"
            />
        </div>

        <div class="form-row">
            <div class="form-group">
                <label for="search-headline">Headline</label>
                <input
                    id="search-headline"
                    type="text"
                    bind:value={searchParams.headline}
                    placeholder="Filter by headline..."
                    data-testid="search-headline"
                />
            </div>

            <div class="form-group">
                <label for="search-keywords">Keywords</label>
                <input
                    id="search-keywords"
                    type="text"
                    bind:value={searchParams.keywords}
                    placeholder="Filter by keywords..."
                    data-testid="search-keywords"
                />
            </div>
        </div>

        <div class="form-row">
            <div class="form-group">
                <label for="search-author">Author</label>
                <input
                    id="search-author"
                    type="text"
                    bind:value={searchParams.author}
                    placeholder="Filter by author..."
                    data-testid="search-author"
                />
            </div>

            <div class="form-group">
                <label for="search-created-after">Created After</label>
                <input
                    id="search-created-after"
                    type="date"
                    bind:value={searchParams.created_after}
                />
            </div>

            <div class="form-group">
                <label for="search-created-before">Created Before</label>
                <input
                    id="search-created-before"
                    type="date"
                    bind:value={searchParams.created_before}
                />
            </div>
        </div>

        <div class="form-actions">
            <button on:click={handleSearch} disabled={searchLoading} data-testid="search-submit">
                {searchLoading ? 'Searching...' : 'Search'}
            </button>
            <button class="btn-secondary" on:click={handleClearSearch} disabled={searchLoading} data-testid="clear-search">
                Clear
            </button>
        </div>
    </div>

    <!-- Search Results -->
    {#if searchLoading}
        <div class="loading-state">Searching articles...</div>
    {:else if searchResults.length > 0}
        <div class="search-results" data-testid="search-results">
            <h3>{searchResults.length} {searchResults.length === 1 ? 'result' : 'results'} found</h3>
            <div class="articles-list">
                {#each searchResults as article}
                    <div class="article-card" on:click={() => handleArticleClick(article)}>
                        <h3>{article.headline}</h3>
                        <div class="article-info">
                            <span class="topic-badge">{article.topic}</span>
                            <span>{formatDate(article.created_at)}</span>
                            <span>Readership: {article.readership_count}</span>
                            {#if article.rating}
                                <span>Rating: {article.rating}/5</span>
                            {/if}
                        </div>
                        {#if article.author}
                            <div class="article-author">
                                <span>Author: {article.author}</span>
                                {#if article.editor}
                                    <span>Editor: {article.editor}</span>
                                {/if}
                            </div>
                        {/if}
                        {#if article.keywords}
                            <div class="article-keywords">
                                {#each article.keywords.split(',').slice(0, 3) as keyword}
                                    <span class="keyword-tag">{keyword.trim()}</span>
                                {/each}
                            </div>
                        {/if}
                    </div>
                {/each}
            </div>
        </div>
    {:else}
        <div class="empty-state">
            <p>Use the search form above to find articles.</p>
        </div>
    {/if}
</div>

<style>
    .search-container {
        flex: 1;
        overflow-y: auto;
        padding: 2rem;
        max-width: 1200px;
        margin: 0 auto;
    }

    .error-message {
        background: #fef2f2;
        color: #dc2626;
        padding: 1rem;
        margin-bottom: 1rem;
        border-radius: 4px;
        border: 1px solid #fecaca;
        font-size: 0.875rem;
    }

    .search-form {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        padding: 2rem;
        margin-bottom: 2rem;
    }

    .search-form h2 {
        margin: 0 0 1.5rem 0;
        color: #1a1a1a;
        font-size: 1.5rem;
        font-weight: 600;
    }

    .form-row {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 1rem;
        margin-bottom: 1rem;
    }

    .form-group {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
    }

    .form-group label {
        font-size: 0.875rem;
        font-weight: 500;
        color: #374151;
    }

    .form-group input,
    .form-group select {
        padding: 0.625rem;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        font-size: 0.875rem;
        font-family: inherit;
    }

    .form-group input:focus,
    .form-group select:focus {
        outline: none;
        border-color: #3b82f6;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
    }

    .form-actions {
        display: flex;
        gap: 0.75rem;
        margin-top: 1.5rem;
    }

    button {
        padding: 0.75rem 1.5rem;
        background: #3b82f6;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.875rem;
        font-weight: 500;
        transition: background 0.2s;
    }

    button:hover:not(:disabled) {
        background: #2563eb;
    }

    button:disabled {
        background: #d1d5db;
        cursor: not-allowed;
    }

    .btn-secondary {
        background: white;
        color: #6b7280;
        border: 1px solid #e5e7eb;
    }

    .btn-secondary:hover:not(:disabled) {
        background: #f9fafb;
        color: #1a1a1a;
    }

    .loading-state,
    .empty-state {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 3rem;
        color: #6b7280;
    }

    .search-results {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        padding: 2rem;
    }

    .search-results h3 {
        margin: 0 0 1.5rem 0;
        color: #1a1a1a;
        font-size: 1.125rem;
        font-weight: 600;
    }

    .articles-list {
        display: grid;
        gap: 1rem;
    }

    .article-card {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        padding: 1.5rem;
        cursor: pointer;
        transition: all 0.2s;
    }

    .article-card:hover {
        border-color: #3b82f6;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
    }

    .article-card h3 {
        margin: 0 0 0.75rem 0;
        color: #1a1a1a;
        font-size: 1.125rem;
        font-weight: 600;
    }

    .article-info {
        display: flex;
        gap: 1.5rem;
        margin-bottom: 0.75rem;
        font-size: 0.875rem;
        color: #6b7280;
    }

    .topic-badge {
        padding: 0.25rem 0.5rem;
        background: #f3f4f6;
        color: #374151;
        border-radius: 2px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
    }

    .article-author {
        display: flex;
        gap: 1.5rem;
        margin-bottom: 0.75rem;
        font-size: 0.875rem;
        color: #6b7280;
        font-style: italic;
    }

    .article-keywords {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
    }

    .keyword-tag {
        padding: 0.25rem 0.5rem;
        background: #eff6ff;
        color: #3b82f6;
        border-radius: 2px;
        font-size: 0.75rem;
        font-weight: 500;
    }
</style>
