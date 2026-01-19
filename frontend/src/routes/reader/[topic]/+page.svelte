<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { getPublishedArticles, getEntitledTopics, type Topic as TopicType } from '$lib/api';
    import { onMount, onDestroy } from 'svelte';
    import { browser } from '$app/environment';
    import { goto } from '$app/navigation';
    import { page } from '$app/stores';
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
    }

    // Get topic from URL params
    $: topic = $page.params.topic;

    let error = '';
    let articles: Article[] = [];
    let articlesLoading = false;

    // Topics loaded from database
    let dbTopics: TopicType[] = [];
    let topicsLoading = false;
    let topicsLoadedForUser: string | null = null;

    // Get current topic info
    $: topicInfo = dbTopics.find(t => t.slug === topic);
    $: topicTitle = topicInfo?.title || topic?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || 'Topic';

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

    async function loadArticles(topicSlug: string) {
        try {
            articlesLoading = true;
            error = '';
            articles = await getPublishedArticles(topicSlug);
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to load articles';
            console.error('Error loading articles:', e);
        } finally {
            articlesLoading = false;
        }
    }

    // Load articles when topic changes
    $: if (topic && $auth.isAuthenticated) {
        loadArticles(topic);
        // Update navigation context
        navigationContext.setContext({
            section: 'reader_topic' as any,
            topic: topic,
            articleId: null,
            articleHeadline: null,
            articleKeywords: null,
            articleStatus: null,
            resourceId: null,
            resourceName: null,
            resourceType: null,
            viewMode: null
        });
    }

    function formatDate(dateString: string) {
        return new Date(dateString).toLocaleDateString();
    }

    function handleArticleClick(article: Article) {
        goto(`/article/${article.id}`);
    }

    // Action handlers
    let actionUnsubscribers: (() => void)[] = [];

    async function handleSelectTopicAction(action: UIAction): Promise<ActionResult> {
        const newTopic = action.params?.topic;
        if (!newTopic) {
            return { success: false, action: 'select_topic', error: 'No topic specified' };
        }
        goto(`/reader/${newTopic}`);
        return { success: true, action: 'select_topic', message: `Switched to ${newTopic}` };
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
        actionUnsubscribers.push(
            actionStore.registerHandler('select_topic', handleSelectTopicAction),
            actionStore.registerHandler('open_article', handleOpenArticleAction)
        );
    });

    onDestroy(() => {
        actionUnsubscribers.forEach(unsub => unsub());
    });
</script>

<div class="reader-container">
    <div class="reader-header">
        <h1>{topicTitle}</h1>
        {#if topicInfo?.description}
            <p class="topic-description">{topicInfo.description}</p>
        {/if}
    </div>

    {#if error}
        <div class="error-message">{error}</div>
    {/if}

    {#if articlesLoading}
        <div class="loading-state">Loading articles...</div>
    {:else if articles.length === 0}
        <div class="empty-state">
            <p>No articles available in this topic yet.</p>
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
    {/if}
</div>

<style>
    .reader-container {
        flex: 1;
        overflow-y: auto;
        padding: 2rem;
        max-width: 1200px;
        margin: 0 auto;
    }

    .reader-header {
        margin-bottom: 2rem;
    }

    .reader-header h1 {
        margin: 0 0 0.5rem 0;
        color: #1a1a1a;
        font-size: 2rem;
        font-weight: 600;
    }

    .topic-description {
        color: #6b7280;
        margin: 0;
        font-size: 1rem;
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
        justify-content: center;
        align-items: center;
        padding: 3rem;
        color: #6b7280;
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
