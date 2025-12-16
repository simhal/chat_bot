<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { sendChatMessage, getAdminArticles, getArticle, downloadArticlePDF } from '$lib/api';
    import { PUBLIC_LINKEDIN_CLIENT_ID, PUBLIC_LINKEDIN_REDIRECT_URI } from '$env/static/public';
    import Markdown from '$lib/components/Markdown.svelte';
    import { onMount, tick } from 'svelte';
    import { browser } from '$app/environment';
    import { page } from '$app/stores';

    type Tab = 'chat' | 'macro' | 'equity' | 'fixed_income' | 'esg';

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

    const tabs = [
        { id: 'chat' as Tab, label: 'Chat' },
        { id: 'macro' as Tab, label: 'Macroeconomic' },
        { id: 'equity' as Tab, label: 'Equity' },
        { id: 'fixed_income' as Tab, label: 'Fixed Income' },
        { id: 'esg' as Tab, label: 'ESG' }
    ];

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
            articles = await getAdminArticles(topic);
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
        } catch (e) {
            console.error('Error loading article:', e);
        }
    }

    function handleTabChange(tab: Tab) {
        currentTab = tab;
        selectedArticle = null;

        // Load articles for the selected topic
        if (tab !== 'chat') {
            loadArticles(tab);
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

    async function handleDeepLink() {
        if (!browser) return;

        const urlParams = new URLSearchParams(window.location.search);
        const tabParam = urlParams.get('tab') as Tab | null;
        const hash = window.location.hash;

        // Switch to tab if specified in URL
        if (tabParam && tabs.some(t => t.id === tabParam)) {
            currentTab = tabParam;
        }

        // Load articles for the current tab
        if (currentTab !== 'chat') {
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
    $: if (browser && $auth.isAuthenticated && $page.url) {
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
                <!-- Tab Navigation -->
                <nav class="tabs">
                    {#each tabs as tab}
                        <button
                            class="tab"
                            class:active={currentTab === tab.id}
                            on:click={() => handleTabChange(tab.id)}
                        >
                            {tab.label}
                        </button>
                    {/each}
                </nav>

                <!-- Tab Content -->
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
                {:else}
                    <div class="articles-container">
                        {#if selectedArticle}
                            <!-- Article Detail View -->
                            <div class="article-detail" id="article-{selectedArticle.id}">
                                <div class="article-actions">
                                    <button class="back-btn" on:click={() => selectedArticle = null}>
                                        Back to articles
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
                        {/if}
                    </div>
                {/if}
            </div>
        {/if}
    </main>
</div>

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

    /* Tabs */
    .tabs {
        display: flex;
        border-bottom: 1px solid #e5e7eb;
        background: white;
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
        height: calc(100vh - 120px);
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
    }

    .download-pdf-btn:hover {
        background: #059669;
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
</style>
