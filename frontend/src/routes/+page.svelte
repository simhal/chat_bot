<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { sendChatMessage, getPublishedArticles, getArticle, downloadArticlePDF, searchArticles, rateArticle, getTopics, getArticlePublicationResources, getPublishedArticleHtmlUrl, getPublishedArticlePdfUrl, type Topic as TopicType, type ArticlePublicationResources } from '$lib/api';
    import { PUBLIC_LINKEDIN_CLIENT_ID, PUBLIC_LINKEDIN_REDIRECT_URI } from '$env/static/public';
    import Markdown from '$lib/components/Markdown.svelte';
    import { onMount, tick } from 'svelte';
    import { browser } from '$app/environment';
    import { page } from '$app/stores';

    // Tab is now dynamic - 'chat', 'search', or any topic slug
    type Tab = string;

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

    let currentTab: Tab = 'chat';
    let messages: Array<{ role: 'user' | 'assistant'; content: string }> = [];
    let inputMessage = '';
    let loading = false;
    let error = '';

    // Articles state
    let articles: Article[] = [];
    let articlesLoading = false;
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
    let topicsLoadedForUser: string | null = null; // Track which user we loaded topics for

    // Dynamic valid tabs based on loaded topics
    $: validTabs = ['chat', 'search', ...dbTopics.filter(t => t.visible && t.active).map(t => t.slug)];

    async function loadTopicsFromDb() {
        if (topicsLoading) return; // Prevent concurrent loads
        try {
            topicsLoading = true;
            dbTopics = await getTopics(true, true); // active_only, visible_only
            topicsLoadedForUser = $auth.user?.email || 'authenticated';
        } catch (e) {
            console.error('Error loading topics:', e);
            dbTopics = [];
            topicsLoadedForUser = null; // Allow retry on error
        } finally {
            topicsLoading = false;
        }
    }

    // Load topics when auth state changes to authenticated
    $: {
        const currentUser = $auth.user?.email || ($auth.isAuthenticated ? 'authenticated' : null);
        if ($auth.isAuthenticated && currentUser !== topicsLoadedForUser && !topicsLoading) {
            loadTopicsFromDb();
        } else if (!$auth.isAuthenticated) {
            dbTopics = [];
            topicsLoadedForUser = null;
        }
    }

    function initiateLinkedInLogin() {
        const state = Math.random().toString(36).substring(7);
        const scope = 'openid profile email';

        const authUrl = new URL('https://www.linkedin.com/oauth/v2/authorization');
        authUrl.searchParams.set('response_type', 'code');
        authUrl.searchParams.set('client_id', PUBLIC_LINKEDIN_CLIENT_ID);
        authUrl.searchParams.set('redirect_uri', PUBLIC_LINKEDIN_REDIRECT_URI);
        authUrl.searchParams.set('scope', scope);
        authUrl.searchParams.set('state', state);

        window.location.href = authUrl.toString();
    }

    async function sendMessage() {
        if (!inputMessage.trim() || loading) return;

        const userMessage = inputMessage.trim();
        inputMessage = '';
        error = '';

        messages = [...messages, { role: 'user', content: userMessage }];
        loading = true;

        try {
            const response = await sendChatMessage(userMessage);
            messages = [...messages, { role: 'assistant', content: response.response }];
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to send message';
            console.error('Error sending message:', e);
        } finally {
            loading = false;
        }
    }

    function handleKeyPress(event: KeyboardEvent) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    }

    async function loadArticles(topic: string) {
        try {
            articlesLoading = true;
            error = '';
            articles = await getPublishedArticles(topic);
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to load articles';
            console.error('Error loading articles:', e);
        } finally {
            articlesLoading = false;
        }
    }

    async function handleArticleClick(article: Article) {
        try {
            // Fetch full article to increment readership
            selectedArticle = await getArticle(article.id);

            // Fetch publication resources for published articles
            try {
                selectedArticleResources = await getArticlePublicationResources(article.id);
            } catch (e) {
                // May not have resources yet (older articles) - that's OK
                selectedArticleResources = null;
            }
        } catch (e) {
            console.error('Error loading article:', e);
        }
    }

    function handleTabChange(tab: Tab) {
        currentTab = tab;
        selectedArticle = null;
        selectedArticleResources = null;

        // Load articles for the selected topic (but not for chat or search)
        if (tab !== 'chat' && tab !== 'search') {
            loadArticles(tab);
        }

        // Reset search results when switching away from search tab
        if (tab !== 'search') {
            searchResults = [];
        }
    }

    function formatDate(dateString: string) {
        return new Date(dateString).toLocaleDateString();
    }

    async function handleDownloadPDF(articleId: number) {
        try {
            error = '';
            await downloadArticlePDF(articleId);
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to download PDF';
        }
    }

    function openRatingModal(article: Article) {
        selectedArticle = article;
        showRatingModal = true;
        userRating = article.user_rating || 0;
    }

    async function handleRateArticle() {
        if (!selectedArticle || userRating === 0) return;

        try {
            error = '';
            await rateArticle(selectedArticle.id, userRating);
            showRatingModal = false;

            // Reload the article to get updated rating
            selectedArticle = await getArticle(selectedArticle.id);

            // Also reload the articles list for the current tab
            if (currentTab !== 'chat' && currentTab !== 'search') {
                await loadArticles(currentTab);
            }

            userRating = 0;
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to rate article';
            console.error('Error rating article:', e);
        }
    }

    async function handleSearch() {
        try {
            searchLoading = true;
            error = '';

            // Build search params object without empty values
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
            topic: 'macro',
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

    async function handleDeepLink() {
        if (!browser) return;

        const urlParams = new URLSearchParams(window.location.search);
        const tabParam = urlParams.get('tab') as Tab | null;
        const hash = window.location.hash;

        // Switch to tab if specified in URL, otherwise default to chat
        if (tabParam && validTabs.includes(tabParam)) {
            currentTab = tabParam;
        } else {
            currentTab = 'chat';
        }

        // Load articles for the current tab (but not for chat or search)
        if (currentTab !== 'chat' && currentTab !== 'search') {
            await loadArticles(currentTab);
        }

        // Handle article deep link (e.g., #article-123)
        if (hash && hash.startsWith('#article-')) {
            const articleIdStr = hash.replace('#article-', '');
            const articleId = parseInt(articleIdStr);

            if (!isNaN(articleId)) {
                // Find the article in the loaded articles
                const article = articles.find(a => a.id === articleId);
                if (article) {
                    await handleArticleClick(article);
                    // Wait for DOM update
                    await tick();
                    // Scroll to article detail
                    const element = document.getElementById(`article-${articleId}`);
                    if (element) {
                        element.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                }
            }
        }
    }

    // React to URL changes
    $: if (browser && $auth.isAuthenticated && $page.url && !topicsLoading) {
        handleDeepLink();
    }

    onMount(() => {
        if ($auth.isAuthenticated) {
            handleDeepLink();
        }
    });
</script>

<div class="app">
    <main>
        {#if !$auth.isAuthenticated}
            <div class="login-container">
                <div class="login-card">
                    <h2>Welcome to Research Platform</h2>
                    <p>Please sign in with LinkedIn to access research and chat</p>
                    <button on:click={initiateLinkedInLogin} class="linkedin-btn">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.32 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.79M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z"/>
                        </svg>
                        Sign in with LinkedIn
                    </button>
                </div>
            </div>
        {:else}
            <div class="content-wrapper">
                <!-- Tab Content (navigation is in the header) -->
                {#if error}
                    <div class="error-message">{error}</div>
                {/if}

                {#if currentTab === 'chat'}
                    <div class="chat-container">
                        <div class="messages">
                            {#if messages.length === 0}
                                <div class="empty-state">
                                    <p>Start a conversation by typing a message below</p>
                                </div>
                            {:else}
                                {#each messages as message}
                                    <div class="message {message.role}">
                                        <div class="message-content">
                                            {#if message.role === 'assistant'}
                                                <Markdown content={message.content} />
                                            {:else}
                                                {message.content}
                                            {/if}
                                        </div>
                                    </div>
                                {/each}
                            {/if}
                            {#if loading}
                                <div class="message assistant loading">
                                    <div class="message-content">
                                        <div class="typing-indicator">
                                            <span></span>
                                            <span></span>
                                            <span></span>
                                        </div>
                                    </div>
                                </div>
                            {/if}
                        </div>

                        <div class="input-container">
                            <div class="input-wrapper">
                                <textarea
                                    bind:value={inputMessage}
                                    on:keypress={handleKeyPress}
                                    placeholder="Type your message..."
                                    rows="1"
                                    disabled={loading}
                                ></textarea>
                                <button on:click={sendMessage} disabled={loading || !inputMessage.trim()}>
                                    Send
                                </button>
                            </div>
                        </div>
                    </div>
                {:else if currentTab === 'search'}
                    <div class="search-container">
                        {#if selectedArticle}
                            <!-- Article Detail View -->
                            <div class="article-detail" id="article-{selectedArticle.id}">
                                <div class="article-actions">
                                    <button class="back-btn" on:click={() => selectedArticle = null}>
                                        Back to search results
                                    </button>
                                    <button class="download-pdf-btn" on:click={() => handleDownloadPDF(selectedArticle.id)}>
                                        Download PDF
                                    </button>
                                </div>
                                <article>
                                    <h1>{selectedArticle.headline}</h1>
                                    <div class="article-meta">
                                        <span>Published: {formatDate(selectedArticle.created_at)}</span>
                                        <span>Readership: {selectedArticle.readership_count}</span>
                                        {#if selectedArticle.rating}
                                            <span>Rating: {selectedArticle.rating}/5</span>
                                        {/if}
                                        {#if selectedArticle.author}
                                            <span>Author: {selectedArticle.author}</span>
                                        {/if}
                                        {#if selectedArticle.editor}
                                            <span>Editor: {selectedArticle.editor}</span>
                                        {/if}
                                    </div>
                                    {#if selectedArticle.keywords}
                                        <div class="keywords">
                                            {#each selectedArticle.keywords.split(',') as keyword}
                                                <span class="keyword-tag">{keyword.trim()}</span>
                                            {/each}
                                        </div>
                                    {/if}
                                    <div class="article-content">
                                        <Markdown content={selectedArticle.content} />
                                    </div>
                                </article>
                            </div>
                        {:else}
                            <!-- Search Form -->
                            <div class="search-form">
                            <h2>Advanced Article Search</h2>

                            <div class="form-row">
                                <div class="form-group">
                                    <label for="search-topic">Topic</label>
                                    <select id="search-topic" bind:value={searchParams.topic}>
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
                                    />
                                </div>

                                <div class="form-group">
                                    <label for="search-keywords">Keywords</label>
                                    <input
                                        id="search-keywords"
                                        type="text"
                                        bind:value={searchParams.keywords}
                                        placeholder="Filter by keywords..."
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
                                <button on:click={handleSearch} disabled={searchLoading}>
                                    {searchLoading ? 'Searching...' : 'Search'}
                                </button>
                                <button class="btn-secondary" on:click={handleClearSearch} disabled={searchLoading}>
                                    Clear
                                </button>
                            </div>
                        </div>

                        <!-- Search Results -->
                        {#if searchLoading}
                            <div class="loading-state">Searching articles...</div>
                        {:else if searchResults.length > 0}
                            <div class="search-results">
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
                        {:else if searchResults.length === 0 && !searchLoading}
                            <div class="empty-state">
                                <p>No results found. Try adjusting your search criteria.</p>
                            </div>
                        {/if}
                        {/if}
                    </div>
                {:else}
                    <div class="articles-container">
                        <!-- Articles List -->
                        {#if articlesLoading}
                                <div class="loading-state">Loading articles...</div>
                            {:else if articles.length === 0}
                                <div class="empty-state">
                                    <p>No articles available in this category yet.</p>
                                </div>
                            {:else}
                                <div class="articles-list">
                                    {#each articles as article}
                                        <div class="article-card" on:click={() => handleArticleClick(article)}>
                                            <h3>{article.headline}</h3>
                                            <div class="article-info">
                                                <span>{formatDate(article.created_at)}</span>
                                                <span>Readership: {article.readership_count}</span>
                                                {#if article.rating}
                                                    <span>Rating: {article.rating}/5</span>
                                                {/if}
                                            </div>
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
                            {/if}
                    </div>
                {/if}
            </div>
        {/if}
    </main>
</div>

<!-- View Article Modal -->
{#if selectedArticle && !showRatingModal}
    <div class="modal-overlay" on:click={() => { selectedArticle = null; selectedArticleResources = null; }}>
        <div class="modal large" on:click|stopPropagation>
            <!-- Fixed Header with Buttons -->
            <div class="modal-header-fixed">
                <div class="modal-header">
                    <h2>{selectedArticle.headline}</h2>
                    <button class="close-btn" on:click={() => { selectedArticle = null; selectedArticleResources = null; }}>×</button>
                </div>
                <div class="modal-actions-fixed">
                    <button on:click={() => { selectedArticle = null; selectedArticleResources = null; }}>← Back to Articles</button>
                    <button class="download-pdf-btn" on:click={() => handleDownloadPDF(selectedArticle.id)}>
                        Download PDF
                    </button>
                    <button class="rate-btn" on:click={() => openRatingModal(selectedArticle)}>
                        Rate Article
                    </button>
                </div>
            </div>

            <!-- Content: HTML iframe or markdown fallback -->
            {#if selectedArticleResources?.hash_ids?.html}
                <iframe
                    src={getPublishedArticleHtmlUrl(selectedArticleResources.hash_ids.html)}
                    title={selectedArticle.headline}
                    class="article-html-iframe"
                ></iframe>
            {:else}
                <!-- Fallback to markdown for articles without HTML resource -->
                <div class="modal-content-scrollable">
                    <div class="modal-meta">
                        <span><strong>Published:</strong> {formatDate(selectedArticle.created_at)}</span>
                        <span><strong>Readership:</strong> {selectedArticle.readership_count}</span>
                        {#if selectedArticle.rating}
                            <span><strong>Rating:</strong> {selectedArticle.rating}/5 ({selectedArticle.rating_count} ratings)</span>
                        {/if}
                        {#if selectedArticle.author}
                            <span><strong>Author:</strong> {selectedArticle.author}</span>
                        {/if}
                        {#if selectedArticle.editor}
                            <span><strong>Editor:</strong> {selectedArticle.editor}</span>
                        {/if}
                    </div>
                    {#if selectedArticle.keywords}
                        <div class="modal-keywords">
                            <strong>Keywords:</strong> {selectedArticle.keywords}
                        </div>
                    {/if}
                    <div class="modal-content">
                        <Markdown content={selectedArticle.content} />
                    </div>
                </div>
            {/if}
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
                        class:selected={star <= userRating}
                        on:click={() => userRating = star}
                    >
                        ⭐
                    </button>
                {/each}
            </div>

            {#if userRating > 0}
                <p class="rating-text">
                    You selected: {userRating} star{userRating !== 1 ? 's' : ''}
                </p>
            {/if}

            <div class="modal-actions">
                <button on:click={handleRateArticle} disabled={userRating === 0}>
                    Submit Rating
                </button>
                <button on:click={() => { showRatingModal = false; userRating = 0; }}>
                    Cancel
                </button>
            </div>
        </div>
    </div>
{/if}

<style>
    :global(body) {
        margin: 0;
        padding: 0;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    }

    .app {
        display: flex;
        flex-direction: column;
        height: 100vh;
        background: #fafafa;
    }

    main {
        flex: 1;
        overflow: hidden;
    }

    .login-container {
        display: flex;
        justify-content: center;
        align-items: center;
        height: 100%;
    }

    .login-card {
        background: white;
        padding: 3rem;
        border-radius: 4px;
        border: 1px solid #e5e7eb;
        text-align: center;
        max-width: 400px;
    }

    .login-card h2 {
        margin: 0 0 1rem;
        color: #1a1a1a;
        font-weight: 600;
    }

    .login-card p {
        color: #6b7280;
        margin-bottom: 2rem;
    }

    .linkedin-btn {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.75rem 1.5rem;
        background: #0077b5;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 1rem;
        font-weight: 500;
        transition: background 0.2s;
    }

    .linkedin-btn:hover {
        background: #006399;
    }

    .content-wrapper {
        display: flex;
        flex-direction: column;
        height: 100%;
        max-width: 1200px;
        margin: 0 auto;
        background: white;
    }

    .error-message {
        background: #fef2f2;
        color: #dc2626;
        padding: 1rem;
        margin: 1rem;
        border-radius: 4px;
        border: 1px solid #fecaca;
        font-size: 0.875rem;
    }

    /* Chat Container */
    .chat-container {
        display: flex;
        flex-direction: column;
        height: calc(100vh - 60px);
    }

    .messages {
        flex: 1;
        overflow-y: auto;
        padding: 2rem;
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }

    .empty-state,
    .loading-state {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 3rem;
        color: #6b7280;
    }

    .message {
        display: flex;
    }

    .message.user {
        justify-content: flex-end;
    }

    .message.assistant {
        justify-content: flex-start;
    }

    .message-content {
        max-width: 70%;
        padding: 0.75rem 1rem;
        border-radius: 8px;
        word-wrap: break-word;
        font-size: 0.95rem;
    }

    .message.user .message-content {
        background: #3b82f6;
        color: white;
    }

    .message.assistant .message-content {
        background: #f3f4f6;
        color: #1a1a1a;
    }

    .typing-indicator {
        display: flex;
        gap: 4px;
    }

    .typing-indicator span {
        width: 8px;
        height: 8px;
        background: #6b7280;
        border-radius: 50%;
        animation: bounce 1.4s infinite;
    }

    .typing-indicator span:nth-child(2) {
        animation-delay: 0.2s;
    }

    .typing-indicator span:nth-child(3) {
        animation-delay: 0.4s;
    }

    @keyframes bounce {
        0%, 60%, 100% {
            transform: translateY(0);
        }
        30% {
            transform: translateY(-10px);
        }
    }

    .input-container {
        border-top: 1px solid #e5e7eb;
        padding: 1rem;
        background: white;
    }

    .input-wrapper {
        display: flex;
        gap: 0.5rem;
    }

    textarea {
        flex: 1;
        padding: 0.75rem;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        font-family: inherit;
        font-size: 0.95rem;
        resize: none;
        min-height: 44px;
        max-height: 200px;
    }

    textarea:focus {
        outline: none;
        border-color: #3b82f6;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
    }

    textarea:disabled {
        background: #f9fafb;
        cursor: not-allowed;
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

    /* Articles Container */
    .articles-container {
        flex: 1;
        overflow-y: auto;
        padding: 2rem;
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

    /* Article Detail */
    .article-detail {
        max-width: 800px;
        margin: 0 auto;
    }

    .article-actions {
        display: flex;
        gap: 1rem;
        margin-bottom: 1.5rem;
    }

    .back-btn {
        padding: 0.5rem 1rem;
        background: white;
        border: 1px solid #e5e7eb;
        color: #6b7280;
    }

    .back-btn:hover {
        background: #f9fafb;
        color: #1a1a1a;
    }

    .download-pdf-btn {
        padding: 0.5rem 1rem;
        background: #10b981;
        color: white;
        border: none;
        text-decoration: none;
        display: inline-block;
        border-radius: 4px;
        font-size: 0.875rem;
        font-weight: 500;
        cursor: pointer;
    }

    .download-pdf-btn:hover {
        background: #059669;
    }

    .view-html-btn {
        padding: 0.5rem 1rem;
        background: #3b82f6;
        color: white;
        border: none;
        text-decoration: none;
        display: inline-block;
        border-radius: 4px;
        font-size: 0.875rem;
        font-weight: 500;
        cursor: pointer;
    }

    .view-html-btn:hover {
        background: #2563eb;
    }

    article h1 {
        margin: 0 0 1rem 0;
        color: #1a1a1a;
        font-size: 2rem;
        font-weight: 700;
        line-height: 1.3;
    }

    .article-meta {
        display: flex;
        gap: 1.5rem;
        margin-bottom: 1.5rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid #e5e7eb;
        font-size: 0.875rem;
        color: #6b7280;
    }

    .keywords {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        margin-bottom: 2rem;
    }

    .article-content {
        line-height: 1.8;
        color: #374151;
        font-size: 1rem;
    }

    /* Search Container */
    .search-container {
        flex: 1;
        overflow-y: auto;
        padding: 2rem;
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

    .btn-secondary {
        background: white;
        color: #6b7280;
        border: 1px solid #e5e7eb;
    }

    .btn-secondary:hover:not(:disabled) {
        background: #f9fafb;
        color: #1a1a1a;
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
        max-width: 1000px;
        width: 80vw;
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

    .modal-header h2 {
        margin: 0;
        color: #333;
        flex: 1;
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
        background: #10b981;
        color: white;
        text-decoration: none;
    }

    .modal-actions-fixed .download-pdf-btn:hover {
        background: #059669;
    }

    .modal-actions-fixed .view-html-btn {
        background: #3b82f6;
        color: white;
        text-decoration: none;
    }

    .modal-actions-fixed .view-html-btn:hover {
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

    .article-html-iframe {
        flex: 1;
        width: 100%;
        min-height: 70vh;
        border: none;
        background: white;
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
        background: #4caf50;
        color: white;
    }

    .modal-actions button:first-child:hover:not(:disabled) {
        background: #45a049;
    }

    .modal-actions button:first-child:disabled {
        background: #ccc;
        cursor: not-allowed;
    }

    .modal-actions button:last-child {
        background: #f5f5f5;
        color: #333;
    }

    .modal-actions button:last-child:hover {
        background: #e0e0e0;
    }
</style>
