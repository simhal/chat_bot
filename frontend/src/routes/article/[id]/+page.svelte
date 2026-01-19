<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { getArticle, getArticleById, downloadArticlePDF, rateArticle, getArticlePublicationResources, getPublishedArticleHtmlUrl, type ArticlePublicationResources } from '$lib/api';
    import Markdown from '$lib/components/Markdown.svelte';
    import { onMount, onDestroy } from 'svelte';
    import { browser } from '$app/environment';
    import { goto } from '$app/navigation';
    import { page } from '$app/stores';
    import { navigationContext } from '$lib/stores/navigation';
    import { actionStore, type UIAction, type ActionResult } from '$lib/stores/actions';

    interface Article {
        id: number;
        topic: string;
        topic_slug?: string;
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

    // Get article ID from URL params
    $: articleId = parseInt($page.params.id || '0');

    let error = '';
    let article: Article | null = null;
    let articleResources: ArticlePublicationResources | null = null;
    let loading = true;
    let showRatingModal = false;
    let userRating = 0;

    // Redirect if not authenticated
    $: if (browser && !$auth.isAuthenticated) {
        goto('/');
    }

    async function loadArticle(id: number) {
        try {
            loading = true;
            error = '';
            // Use getArticleById which fetches by ID without requiring topic
            article = await getArticleById(id);

            // Update navigation context
            if (article) {
                const topicSlug = article.topic_slug || article.topic;
                navigationContext.setArticle(article.id, article.headline, article.keywords, 'published');
                navigationContext.setContext({
                    section: 'home',
                    topic: topicSlug,
                    subNav: null,
                    articleId: article.id,
                    articleHeadline: article.headline,
                    articleKeywords: article.keywords,
                    articleStatus: 'published',
                    role: 'reader'
                });

                // Try to load resources
                try {
                    articleResources = await getArticlePublicationResources(topicSlug, article.id);
                } catch (e) {
                    articleResources = null;
                }
            }
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to load article';
            console.error('Error loading article:', e);
        } finally {
            loading = false;
        }
    }

    // Load article when ID changes
    $: if (articleId && !isNaN(articleId) && $auth.isAuthenticated) {
        loadArticle(articleId);
    }

    function formatDate(dateString: string) {
        return new Date(dateString).toLocaleDateString();
    }

    async function handleDownloadPDF() {
        if (!article) return;
        try {
            error = '';
            const topicSlug = article.topic_slug || article.topic;
            await downloadArticlePDF(topicSlug, article.id);
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to download PDF';
        }
    }

    function openRatingModal() {
        if (!article) return;
        showRatingModal = true;
        userRating = article.user_rating || 0;
    }

    async function handleRateArticle() {
        if (!article || userRating === 0) return;

        try {
            error = '';
            const topicSlug = article.topic_slug || article.topic;
            await rateArticle(topicSlug, article.id, userRating);
            showRatingModal = false;
            // Reload article to get updated rating
            await loadArticle(article.id);
            userRating = 0;
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to rate article';
            console.error('Error rating article:', e);
        }
    }

    function handleBack() {
        if (article) {
            const topicSlug = article.topic_slug || article.topic;
            goto(`/reader/${topicSlug}`);
        } else {
            goto('/');
        }
    }

    // Action handlers
    let actionUnsubscribers: (() => void)[] = [];

    async function handleRateArticleAction(action: UIAction): Promise<ActionResult> {
        const rating = action.params?.rating;
        if (!article) {
            return { success: false, action: 'rate_article', error: 'No article loaded' };
        }
        if (rating) {
            userRating = rating;
            await handleRateArticle();
            return { success: true, action: 'rate_article', message: `Rated article ${rating} stars` };
        } else {
            openRatingModal();
            return { success: true, action: 'rate_article', message: 'Rating dialog opened' };
        }
    }

    async function handleDownloadPdfAction(action: UIAction): Promise<ActionResult> {
        if (!article) {
            return { success: false, action: 'download_pdf', error: 'No article loaded' };
        }
        try {
            await handleDownloadPDF();
            return { success: true, action: 'download_pdf', message: `PDF downloaded for article #${article.id}` };
        } catch (e) {
            return { success: false, action: 'download_pdf', error: e instanceof Error ? e.message : 'Failed to download PDF' };
        }
    }

    async function handleEditArticleAction(action: UIAction): Promise<ActionResult> {
        if (!article) {
            return { success: false, action: 'edit_article', error: 'No article loaded' };
        }
        const topicSlug = article.topic_slug || article.topic;
        goto(`/analyst/${topicSlug}/edit/${article.id}`);
        return { success: true, action: 'edit_article', message: `Opening article #${article.id} for editing` };
    }

    onMount(() => {
        actionUnsubscribers.push(
            actionStore.registerHandler('rate_article', handleRateArticleAction),
            actionStore.registerHandler('download_pdf', handleDownloadPdfAction),
            actionStore.registerHandler('edit_article', handleEditArticleAction)
        );
    });

    onDestroy(() => {
        actionUnsubscribers.forEach(unsub => unsub());
        navigationContext.clearArticle();
    });
</script>

<div class="article-container">
    {#if error}
        <div class="error-message">{error}</div>
    {/if}

    {#if loading}
        <div class="loading-state">Loading article...</div>
    {:else if article}
        <div class="article-header">
            <div class="article-actions">
                <button class="back-btn" on:click={handleBack} data-testid="back-btn">
                    Back to {article.topic_slug || article.topic}
                </button>
                <button class="download-pdf-btn" on:click={handleDownloadPDF} data-testid="download-pdf">
                    Download PDF
                </button>
                <button class="rate-btn" on:click={openRatingModal} data-testid="rate-btn">
                    Rate Article
                </button>
            </div>
        </div>

        <!-- Content: Popup iframe or markdown fallback -->
        {#if articleResources?.hash_ids?.popup}
            <div class="article-iframe-container">
                <iframe
                    src={getPublishedArticleHtmlUrl(articleResources.hash_ids.popup)}
                    title={article.headline}
                    class="article-html-iframe"
                ></iframe>
            </div>
        {:else}
            <article class="article-content" data-testid="article-content">
                <h1>{article.headline}</h1>
                <div class="article-meta">
                    <span data-testid="article-date">Published: {formatDate(article.created_at)}</span>
                    <span>Readership: {article.readership_count}</span>
                    {#if article.rating}
                        <span>Rating: {article.rating}/5 ({article.rating_count} ratings)</span>
                    {/if}
                    {#if article.author}
                        <span data-testid="article-author">Author: {article.author}</span>
                    {/if}
                    {#if article.editor}
                        <span>Editor: {article.editor}</span>
                    {/if}
                </div>
                {#if article.keywords}
                    <div class="keywords">
                        {#each article.keywords.split(',') as keyword}
                            <span class="keyword-tag">{keyword.trim()}</span>
                        {/each}
                    </div>
                {/if}
                <div class="article-body">
                    <Markdown content={article.content} />
                </div>
            </article>
        {/if}
    {:else}
        <div class="empty-state">
            <p>Article not found.</p>
            <button on:click={() => goto('/')}>Go to Home</button>
        </div>
    {/if}
</div>

<!-- Rating Modal -->
{#if showRatingModal && article}
    <div class="modal-overlay" on:click={() => { showRatingModal = false; userRating = 0; }}>
        <div class="modal" on:click|stopPropagation>
            <h3>Rate Article</h3>
            <p class="article-title">{article.headline}</p>

            <div class="rating-selector" data-testid="rating-control">
                {#each [1, 2, 3, 4, 5] as star}
                    <button
                        class="star-btn"
                        class:selected={star <= userRating}
                        on:click={() => userRating = star}
                        data-testid="rating-star-{star}"
                    >
                        *
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
    .article-container {
        flex: 1;
        overflow-y: auto;
        padding: 2rem;
        max-width: 1000px;
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

    .loading-state,
    .empty-state {
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        padding: 3rem;
        color: #6b7280;
        gap: 1rem;
    }

    .article-header {
        margin-bottom: 2rem;
    }

    .article-actions {
        display: flex;
        gap: 1rem;
        flex-wrap: wrap;
    }

    .article-actions button {
        padding: 0.5rem 1rem;
        border-radius: 4px;
        font-size: 0.875rem;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s;
    }

    .back-btn {
        background: white;
        border: 1px solid #e5e7eb;
        color: #6b7280;
    }

    .back-btn:hover {
        background: #f9fafb;
        color: #1a1a1a;
    }

    .download-pdf-btn {
        background: #10b981;
        color: white;
        border: none;
    }

    .download-pdf-btn:hover {
        background: #059669;
    }

    .rate-btn {
        background: #4caf50;
        color: white;
        border: none;
    }

    .rate-btn:hover {
        background: #45a049;
    }

    .article-iframe-container {
        height: calc(100vh - 200px);
        min-height: 500px;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        overflow: hidden;
    }

    .article-html-iframe {
        width: 100%;
        height: 100%;
        border: none;
        background: white;
    }

    .article-content {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 2rem;
    }

    .article-content h1 {
        margin: 0 0 1rem 0;
        color: #1a1a1a;
        font-size: 2rem;
        font-weight: 700;
        line-height: 1.3;
    }

    .article-meta {
        display: flex;
        flex-wrap: wrap;
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

    .keyword-tag {
        padding: 0.25rem 0.5rem;
        background: #eff6ff;
        color: #3b82f6;
        border-radius: 2px;
        font-size: 0.75rem;
        font-weight: 500;
    }

    .article-body {
        line-height: 1.8;
        color: #374151;
        font-size: 1rem;
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
        color: #fbbf24;
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
</style>
