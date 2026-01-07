<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { getAdminArticles, deleteArticle, reactivateArticle, recallArticle, purgeArticle, getPromptModules, updatePromptModule, reorderArticles, editArticle, getGroupResources, deleteResource, getTopics, type PromptModule, type Resource, type Topic } from '$lib/api';
    import { onMount, onDestroy } from 'svelte';
    import { goto } from '$app/navigation';
    import { page } from '$app/stores';
    import ResourceEditor from '$lib/components/ResourceEditor.svelte';
    import { navigationContext } from '$lib/stores/navigation';
    import { actionStore, type UIAction, type ActionResult } from '$lib/stores/actions';

    // Topics loaded from database
    let allTopics: Array<{ id: string; label: string }> = [];
    let dbTopics: Topic[] = [];
    let topicsLoading = true;

    let articles: any[] = [];
    let loading = true;
    let articlesLoading = false;
    let error = '';

    // Topic-specific prompt editing
    let topicPrompt: PromptModule | null = null;
    let topicPromptLoading = false;
    let showTopicPromptModal = false;
    let topicPromptEdited = '';
    let topicPromptSaving = false;

    // Resource management state
    let resources: Resource[] = [];
    let resourcesLoading = false;
    let resourcesTotal = 0;
    let topicSubView: 'articles' | 'resources' = 'articles';

    // View state
    let selectedTopic: string = '';
    let initialViewSet = false;

    // Persist selected topic to localStorage (shared across analyst, editor, admin)
    const SELECTED_TOPIC_KEY = 'selected_topic';

    function saveSelectedTopic(topic: string) {
        if (typeof localStorage !== 'undefined') {
            localStorage.setItem(SELECTED_TOPIC_KEY, topic);
        }
    }

    function getSavedTopic(): string | null {
        if (typeof localStorage !== 'undefined') {
            return localStorage.getItem(SELECTED_TOPIC_KEY);
        }
        return null;
    }

    // Article drag and drop state
    let draggedArticle: any = null;
    let dragOverArticleIndex: number | null = null;

    // Check permissions
    $: isGlobalAdmin = $auth.user?.scopes?.includes('global:admin') || false;

    // Topic tabs are visible based on {topic}:admin scope or global:admin
    $: adminTopics = allTopics.filter(topic => {
        if (!$auth.user?.scopes) return false;
        if ($auth.user.scopes.includes('global:admin')) return true;
        return $auth.user.scopes.includes(`${topic.id}:admin`);
    });

    $: hasAdminAccess = isGlobalAdmin || adminTopics.length > 0;

    // Redirect if no admin access
    $: if ($auth.isAuthenticated && !hasAdminAccess) {
        goto('/');
    }

    // Set default topic when permissions and topics are loaded
    $: if (!initialViewSet && $auth.isAuthenticated && !topicsLoading && adminTopics.length > 0) {
        // Check for topic in URL query parameter first (from navigation)
        const urlTopic = $page.url.searchParams.get('topic');
        if (urlTopic && adminTopics.some(t => t.id === urlTopic)) {
            selectedTopic = urlTopic;
        } else {
            // Try to restore saved topic if it's accessible to the user
            const savedTopic = getSavedTopic();
            if (savedTopic && adminTopics.some(t => t.id === savedTopic)) {
                selectedTopic = savedTopic;
            } else {
                selectedTopic = adminTopics[0].id;
            }
        }
        initialViewSet = true;
    }

    // Save selected topic when it changes
    $: if (selectedTopic && initialViewSet) {
        saveSelectedTopic(selectedTopic);
    }

    // Update navigation context when selected topic changes
    $: if (initialViewSet && selectedTopic) {
        navigationContext.setContext({
            section: 'admin',
            topic: selectedTopic,
            subNav: topicSubView,
            articleId: null,
            articleHeadline: null,
            role: 'admin'
        });
    }

    async function loadTopicsFromDb() {
        try {
            topicsLoading = true;
            dbTopics = await getTopics();
            allTopics = dbTopics.map(t => ({ id: t.slug, label: t.title }));
        } catch (e) {
            console.error('Error loading topics:', e);
            allTopics = [];
            dbTopics = [];
        } finally {
            topicsLoading = false;
        }
    }

    async function loadData() {
        try {
            loading = true;
            error = '';
            await loadTopicsFromDb();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to load admin data';
            console.error('Error loading admin data:', e);
        } finally {
            loading = false;
        }
    }

    async function loadArticles(topic: string) {
        try {
            articlesLoading = true;
            error = '';
            const allArticles = await getAdminArticles(topic, 0, 100);
            // Sort by: sticky first, then by priority (descending), then by date
            articles = allArticles.sort((a: any, b: any) => {
                if (a.is_sticky !== b.is_sticky) {
                    return a.is_sticky ? -1 : 1;
                }
                if ((b.priority || 0) !== (a.priority || 0)) {
                    return (b.priority || 0) - (a.priority || 0);
                }
                return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
            });
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to load articles';
            console.error('Error loading articles:', e);
        } finally {
            articlesLoading = false;
        }
    }

    $: if (selectedTopic && topicSubView === 'articles') {
        loadArticles(selectedTopic);
    }

    $: if (selectedTopic && topicSubView === 'resources') {
        loadTopicResources(selectedTopic);
    }

    function handleTopicResourceRefresh() {
        if (selectedTopic) {
            loadTopicResources(selectedTopic);
        }
    }

    function handleResourceError(event: CustomEvent<string>) {
        error = event.detail;
    }

    async function loadTopicResources(topic: string) {
        try {
            resourcesLoading = true;
            error = '';
            const response = await getGroupResources(topic);
            resources = response.resources;
            resourcesTotal = response.total;
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to load resources';
            console.error('Error loading resources:', e);
        } finally {
            resourcesLoading = false;
        }
    }

    async function handleDeleteArticle(articleId: number) {
        if (!confirm('Are you sure you want to deactivate this article?')) return;
        try {
            error = '';
            await deleteArticle(selectedTopic, articleId);
            await loadArticles(selectedTopic);
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to deactivate article';
        }
    }

    async function handleReactivateArticle(articleId: number) {
        if (!confirm('Are you sure you want to reactivate this article?')) return;
        try {
            error = '';
            await reactivateArticle(selectedTopic, articleId);
            await loadArticles(selectedTopic);
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to reactivate article';
        }
    }

    async function handleRecallArticle(articleId: number) {
        if (!confirm('Are you sure you want to recall this published article to draft?')) return;
        try {
            error = '';
            await recallArticle(selectedTopic, articleId);
            await loadArticles(selectedTopic);
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to recall article';
        }
    }

    async function handlePurgeArticle(articleId: number) {
        if (!confirm('WARNING: This will PERMANENTLY DELETE this article and all its data. This action cannot be undone. Are you sure?')) return;
        if (!confirm('This is your final warning. The article will be permanently destroyed. Continue?')) return;
        try {
            error = '';
            await purgeArticle(articleId);
            await loadArticles(selectedTopic);
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to purge article';
        }
    }

    function getStatusLabel(status: string) {
        switch (status) {
            case 'draft': return 'Draft';
            case 'editor': return 'In Review';
            case 'published': return 'Published';
            default: return status;
        }
    }

    function getStatusClass(status: string) {
        switch (status) {
            case 'draft': return 'status-draft';
            case 'editor': return 'status-editor';
            case 'published': return 'status-published';
            default: return '';
        }
    }

    // Topic prompt management
    async function loadTopicPrompt(topic: string) {
        try {
            topicPromptLoading = true;
            const allPrompts = await getPromptModules();
            // Find the content_topic prompt for this specific topic
            topicPrompt = allPrompts.find(p =>
                p.prompt_type === 'content_topic' &&
                p.prompt_group === topic
            ) || null;
            if (topicPrompt) {
                topicPromptEdited = topicPrompt.template_text;
            }
        } catch (e) {
            console.error('Error loading topic prompt:', e);
            topicPrompt = null;
        } finally {
            topicPromptLoading = false;
        }
    }

    function openTopicPromptModal() {
        if (selectedTopic) {
            loadTopicPrompt(selectedTopic);
            showTopicPromptModal = true;
        }
    }

    async function saveTopicPrompt() {
        if (!topicPrompt || !topicPromptEdited.trim()) return;
        try {
            topicPromptSaving = true;
            await updatePromptModule(topicPrompt.id, {
                template_text: topicPromptEdited
            });
            showTopicPromptModal = false;
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to save topic prompt';
        } finally {
            topicPromptSaving = false;
        }
    }

    // Article sticky toggle
    async function toggleArticleSticky(article: any) {
        try {
            error = '';
            await editArticle(article.topic, article.id, undefined, undefined, undefined, undefined, undefined, !article.is_sticky);
            await loadArticles(selectedTopic);
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to toggle sticky';
        }
    }

    // Article drag and drop
    function handleArticleDragStart(event: DragEvent, article: any) {
        draggedArticle = article;
        if (event.dataTransfer) {
            event.dataTransfer.effectAllowed = 'move';
        }
    }

    function handleArticleDragOver(event: DragEvent, index: number) {
        event.preventDefault();
        if (event.dataTransfer) {
            event.dataTransfer.dropEffect = 'move';
        }
        dragOverArticleIndex = index;
    }

    function handleArticleDragLeave() {
        dragOverArticleIndex = null;
    }

    async function handleArticleDrop(event: DragEvent, targetIndex: number) {
        event.preventDefault();
        if (!draggedArticle || !selectedTopic) return;

        const sourceIndex = articles.findIndex(a => a.id === draggedArticle.id);
        if (sourceIndex === targetIndex) {
            draggedArticle = null;
            dragOverArticleIndex = null;
            return;
        }

        // Reorder locally first for instant feedback
        const newArticles = [...articles];
        const [removed] = newArticles.splice(sourceIndex, 1);
        newArticles.splice(targetIndex, 0, removed);
        articles = newArticles;

        // Get the new order of article IDs
        const articleIds = newArticles.map(a => a.id);

        try {
            await reorderArticles(selectedTopic, articleIds);
            // Reload to get updated priorities
            await loadArticles(selectedTopic);
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to reorder articles';
            // Reload to restore original order
            await loadArticles(selectedTopic);
        }

        draggedArticle = null;
        dragOverArticleIndex = null;
    }

    function handleArticleDragEnd() {
        draggedArticle = null;
        dragOverArticleIndex = null;
    }

    // Handle article selection - update navigation context
    function handleArticleSelect(article: any) {
        navigationContext.setContext({
            section: 'admin',
            topic: selectedTopic,
            subNav: topicSubView,
            articleId: article.id,
            articleHeadline: article.headline,
            role: 'admin'
        });
    }

    onMount(() => {
        loadData();
    });

    // Action handlers for chatbot-triggered UI actions
    async function handleDeactivateArticleAction(action: UIAction): Promise<ActionResult> {
        const articleId = action.params?.article_id;
        if (!articleId) {
            return { success: false, action: 'deactivate_article', error: 'No article ID specified' };
        }
        if (!action.params?.confirmed) {
            return { success: false, action: 'deactivate_article', error: 'Action requires confirmation' };
        }
        const topic = action.params?.topic || selectedTopic;
        if (!topic) {
            return { success: false, action: 'deactivate_article', error: 'Cannot determine article topic' };
        }
        try {
            await deleteArticle(topic, articleId);
            await loadArticles(selectedTopic);
            return { success: true, action: 'deactivate_article', message: `Article #${articleId} deactivated` };
        } catch (e) {
            return { success: false, action: 'deactivate_article', error: e instanceof Error ? e.message : 'Failed to deactivate' };
        }
    }

    async function handleReactivateArticleAction(action: UIAction): Promise<ActionResult> {
        const articleId = action.params?.article_id;
        if (!articleId) {
            return { success: false, action: 'reactivate_article', error: 'No article ID specified' };
        }
        if (!action.params?.confirmed) {
            return { success: false, action: 'reactivate_article', error: 'Action requires confirmation' };
        }
        const topic = action.params?.topic || selectedTopic;
        if (!topic) {
            return { success: false, action: 'reactivate_article', error: 'Cannot determine article topic' };
        }
        try {
            await reactivateArticle(topic, articleId);
            await loadArticles(selectedTopic);
            return { success: true, action: 'reactivate_article', message: `Article #${articleId} reactivated` };
        } catch (e) {
            return { success: false, action: 'reactivate_article', error: e instanceof Error ? e.message : 'Failed to reactivate' };
        }
    }

    async function handleRecallArticleAction(action: UIAction): Promise<ActionResult> {
        const articleId = action.params?.article_id;
        if (!articleId) {
            return { success: false, action: 'recall_article', error: 'No article ID specified' };
        }
        if (!action.params?.confirmed) {
            return { success: false, action: 'recall_article', error: 'Action requires confirmation' };
        }
        const topic = action.params?.topic || selectedTopic;
        if (!topic) {
            return { success: false, action: 'recall_article', error: 'Cannot determine article topic' };
        }
        try {
            await recallArticle(topic, articleId);
            await loadArticles(selectedTopic);
            return { success: true, action: 'recall_article', message: `Article #${articleId} recalled to draft` };
        } catch (e) {
            return { success: false, action: 'recall_article', error: e instanceof Error ? e.message : 'Failed to recall' };
        }
    }

    async function handlePurgeArticleAction(action: UIAction): Promise<ActionResult> {
        const articleId = action.params?.article_id;
        if (!articleId) {
            return { success: false, action: 'purge_article', error: 'No article ID specified' };
        }
        if (!action.params?.confirmed) {
            return { success: false, action: 'purge_article', error: 'Action requires confirmation' };
        }
        try {
            await purgeArticle(articleId);
            await loadArticles(selectedTopic);
            return { success: true, action: 'purge_article', message: `Article #${articleId} permanently purged` };
        } catch (e) {
            return { success: false, action: 'purge_article', error: e instanceof Error ? e.message : 'Failed to purge' };
        }
    }

    // Action handler for topic selection
    async function handleSelectTopicAction(action: UIAction): Promise<ActionResult> {
        const topicSlug = action.params?.topic;
        if (!topicSlug) {
            return { success: false, action: 'select_topic', error: 'No topic specified' };
        }
        // Check if user has access to this topic
        if (!adminTopics.some(t => t.id === topicSlug)) {
            return { success: false, action: 'select_topic', error: `No admin access to topic: ${topicSlug}` };
        }
        selectedTopic = topicSlug;
        topicSubView = 'articles'; // Default to articles view
        return { success: true, action: 'select_topic', message: `Switched to topic: ${topicSlug}` };
    }

    // Action handler for focus on article
    async function handleFocusArticleAction(action: UIAction): Promise<ActionResult> {
        const articleId = action.params?.article_id;
        if (!articleId) {
            return { success: false, action: 'focus_article', error: 'No article ID specified' };
        }
        // Find the article in the current list
        const article = articles.find(a => a.id === articleId);
        if (article) {
            handleArticleSelect(article);
            return { success: true, action: 'focus_article', message: `Focused on article #${articleId}` };
        }
        return { success: false, action: 'focus_article', error: `Article #${articleId} not found in current view` };
    }

    // Register action handlers
    let actionUnsubscribers: (() => void)[] = [];

    onMount(() => {
        actionUnsubscribers.push(
            actionStore.registerHandler('select_topic', handleSelectTopicAction),
            actionStore.registerHandler('focus_article', handleFocusArticleAction),
            actionStore.registerHandler('deactivate_article', handleDeactivateArticleAction),
            actionStore.registerHandler('reactivate_article', handleReactivateArticleAction),
            actionStore.registerHandler('recall_article', handleRecallArticleAction),
            actionStore.registerHandler('purge_article', handlePurgeArticleAction)
        );
    });

    onDestroy(() => {
        actionUnsubscribers.forEach(unsub => unsub());
    });
</script>

<div class="admin-container">
    <!-- Header with topic dropdown and action buttons -->
    <div class="admin-header">
        <div class="header-left">
            {#if adminTopics.length > 0}
                <div class="topic-selector">
                    <label for="admin-topic-select">Topic:</label>
                    <select
                        id="admin-topic-select"
                        value={selectedTopic}
                        on:change={(e) => { selectedTopic = e.currentTarget.value; }}
                    >
                        {#each adminTopics as topic}
                            <option value={topic.id}>{topic.label}</option>
                        {/each}
                    </select>
                </div>
                <button
                    class="action-btn"
                    class:active={topicSubView === 'articles'}
                    on:click={() => { topicSubView = 'articles'; }}
                >
                    Articles
                </button>
                <button
                    class="action-btn"
                    class:active={topicSubView === 'resources'}
                    on:click={() => { topicSubView = 'resources'; }}
                >
                    Resources
                </button>
                <button
                    class="action-btn prompt-btn"
                    on:click={openTopicPromptModal}
                >
                    Topic Prompt
                </button>
            {:else}
                <p class="no-access">No topics available. Contact an administrator.</p>
            {/if}
        </div>
    </div>

    {#if error}
        <div class="error-message">{error}</div>
    {/if}

    {#if loading}
        <div class="loading">Loading...</div>
    {:else if selectedTopic}
        <!-- Articles Sub-View -->
        {#if topicSubView === 'articles'}
            <section class="section">
                {#if articlesLoading}
                    <div class="loading">Loading articles...</div>
                {:else if articles.length === 0}
                    <p class="no-articles">No articles found for this topic.</p>
                {:else}
                    <p class="articles-hint">Drag rows to reorder articles by priority. Sticky articles always appear first.</p>
                    <div class="articles-table">
                        <table>
                            <thead>
                                <tr>
                                    <th class="col-priority">#</th>
                                    <th class="col-sticky">Pin</th>
                                    <th>Title</th>
                                    <th>Status</th>
                                    <th>Author</th>
                                    <th>Editor</th>
                                    <th>Reads</th>
                                    <th>Rating</th>
                                    <th>Created</th>
                                    <th>Active</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {#each articles as article, index}
                                    <tr
                                        class:inactive={!article.is_active}
                                        class:sticky-article={article.is_sticky}
                                        class:dragging-article={draggedArticle?.id === article.id}
                                        class:drag-over-article={dragOverArticleIndex === index}
                                        draggable="true"
                                        on:dragstart={(e) => handleArticleDragStart(e, article)}
                                        on:dragover={(e) => handleArticleDragOver(e, index)}
                                        on:dragleave={handleArticleDragLeave}
                                        on:drop={(e) => handleArticleDrop(e, index)}
                                        on:dragend={handleArticleDragEnd}
                                    >
                                        <td class="col-priority">
                                            <span class="drag-handle" title="Drag to reorder">&#x2630;</span>
                                            <span class="priority-number">{article.priority || 0}</span>
                                        </td>
                                        <td class="col-sticky">
                                            <button
                                                class="sticky-btn"
                                                class:is-sticky={article.is_sticky}
                                                on:click={() => toggleArticleSticky(article)}
                                                title={article.is_sticky ? 'Unpin article' : 'Pin article to top'}
                                            >
                                                {article.is_sticky ? '📌' : '📍'}
                                            </button>
                                        </td>
                                        <td class="article-title clickable" on:click={() => handleArticleSelect(article)} title="Click to focus chat on this article">{article.headline}</td>
                                        <td>
                                            <span class="status-badge {getStatusClass(article.status)}">
                                                {getStatusLabel(article.status)}
                                            </span>
                                        </td>
                                        <td>{article.author || '-'}</td>
                                        <td>{article.editor || '-'}</td>
                                        <td class="reads-count">{article.readership_count || 0}</td>
                                        <td class="rating-cell">
                                            {#if article.rating}
                                                {article.rating.toFixed(1)} ({article.rating_count})
                                            {:else}
                                                -
                                            {/if}
                                        </td>
                                        <td>{new Date(article.created_at).toLocaleDateString()}</td>
                                        <td>
                                            <span class="active-badge" class:active={article.is_active} class:inactive-badge={!article.is_active}>
                                                {article.is_active ? 'Yes' : 'No'}
                                            </span>
                                        </td>
                                        <td class="action-buttons">
                                            {#if article.is_active}
                                                {#if article.status === 'published'}
                                                    <button
                                                        class="recall-btn"
                                                        on:click={() => handleRecallArticle(article.id)}
                                                    >
                                                        Recall
                                                    </button>
                                                {/if}
                                                <button
                                                    class="delete-btn"
                                                    on:click={() => handleDeleteArticle(article.id)}
                                                >
                                                    Deactivate
                                                </button>
                                            {:else}
                                                <button
                                                    class="reactivate-btn"
                                                    on:click={() => handleReactivateArticle(article.id)}
                                                >
                                                    Reactivate
                                                </button>
                                            {/if}
                                            <button
                                                class="purge-btn"
                                                on:click={() => handlePurgeArticle(article.id)}
                                            >
                                                Purge
                                            </button>
                                        </td>
                                    </tr>
                                {/each}
                            </tbody>
                        </table>
                    </div>
                {/if}
            </section>
        {/if}

        <!-- Resources Sub-View -->
        {#if topicSubView === 'resources'}
            <section class="section">
                <div class="resources-header">
                    <p class="resources-hint">Shared resources for {allTopics.find(t => t.id === selectedTopic)?.label} group. These resources can be linked to articles.</p>
                </div>
                <div class="resources-editor-container">
                    <ResourceEditor
                        {resources}
                        groupName={selectedTopic}
                        loading={resourcesLoading}
                        showDeleteButton={true}
                        showUnlinkButton={false}
                        on:refresh={handleTopicResourceRefresh}
                        on:error={handleResourceError}
                    />
                </div>
            </section>
        {/if}
    {:else}
        <div class="no-topic-selected">
            <p>Select a topic to manage its articles and resources.</p>
        </div>
    {/if}
</div>

<!-- Topic Prompt Modal -->
{#if showTopicPromptModal}
    <div class="modal-overlay" on:click={() => showTopicPromptModal = false}>
        <div class="modal prompt-modal" on:click|stopPropagation>
            <h3>Edit Topic Prompt: {selectedTopic}</h3>
            <p class="modal-hint">This prompt is used by the content agent when generating articles for this topic.</p>

            {#if topicPromptLoading}
                <div class="loading">Loading prompt...</div>
            {:else if topicPrompt}
                <div class="prompt-edit-form">
                    <div class="form-group">
                        <label for="topic-prompt-template">Topic Prompt Template</label>
                        <textarea
                            id="topic-prompt-template"
                            bind:value={topicPromptEdited}
                            rows="15"
                            placeholder="Enter the topic-specific prompt..."
                        ></textarea>
                    </div>
                </div>

                <div class="modal-actions">
                    <button
                        class="primary"
                        on:click={saveTopicPrompt}
                        disabled={topicPromptSaving || !topicPromptEdited.trim()}
                    >
                        {topicPromptSaving ? 'Saving...' : 'Save Changes'}
                    </button>
                    <button on:click={() => showTopicPromptModal = false}>Cancel</button>
                </div>
            {:else}
                <p class="no-prompt">No topic prompt found for this topic. Please create one in Global Admin.</p>
                <div class="modal-actions">
                    <button on:click={() => showTopicPromptModal = false}>Close</button>
                </div>
            {/if}
        </div>
    </div>
{/if}

<style>
    .admin-container {
        max-width: 1400px;
        margin: 0 auto;
        padding: 1rem 2rem;
    }

    .admin-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1.5rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid #e5e7eb;
    }

    .header-left {
        display: flex;
        gap: 0.75rem;
        align-items: center;
    }

    .topic-selector {
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .topic-selector label {
        font-weight: 500;
        color: #374151;
    }

    .topic-selector select {
        padding: 0.5rem 1rem;
        border: 1px solid #d1d5db;
        border-radius: 6px;
        font-size: 0.875rem;
        background: white;
        min-width: 150px;
    }

    .action-btn {
        padding: 0.5rem 1rem;
        border: 1px solid #d1d5db;
        border-radius: 6px;
        background: white;
        font-size: 0.875rem;
        font-weight: 500;
        color: #374151;
        cursor: pointer;
        transition: all 0.2s;
    }

    .action-btn:hover {
        background: #f9fafb;
        border-color: #9ca3af;
    }

    .action-btn.active {
        background: #3b82f6;
        color: white;
        border-color: #3b82f6;
    }

    .prompt-btn {
        background: #f3f4f6;
    }

    .prompt-btn:hover {
        background: #e5e7eb;
    }

    .no-access {
        color: #6b7280;
        font-style: italic;
    }

    .error-message {
        background: #fef2f2;
        color: #dc2626;
        padding: 1rem;
        margin-bottom: 1rem;
        border-radius: 6px;
        border: 1px solid #fecaca;
    }

    .loading {
        text-align: center;
        padding: 2rem;
        color: #6b7280;
    }

    .section {
        margin-bottom: 2rem;
    }

    .no-articles, .no-topic-selected {
        text-align: center;
        padding: 3rem;
        color: #6b7280;
        background: #f9fafb;
        border-radius: 8px;
    }

    .articles-hint, .resources-hint {
        color: #6b7280;
        font-size: 0.875rem;
        margin-bottom: 1rem;
    }

    .articles-table {
        overflow-x: auto;
    }

    .articles-table table {
        width: 100%;
        border-collapse: collapse;
    }

    .articles-table th,
    .articles-table td {
        padding: 0.75rem;
        text-align: left;
        border-bottom: 1px solid #e5e7eb;
    }

    .articles-table th {
        background: #f9fafb;
        font-weight: 600;
        font-size: 0.75rem;
        text-transform: uppercase;
        color: #6b7280;
    }

    .articles-table tr:hover {
        background: #f9fafb;
    }

    .articles-table tr.inactive {
        opacity: 0.6;
        background: #fef2f2;
    }

    .articles-table tr.sticky-article {
        background: #fef9c3;
    }

    .articles-table tr.dragging-article {
        opacity: 0.5;
    }

    .articles-table tr.drag-over-article {
        border-top: 2px solid #3b82f6;
    }

    .col-priority {
        width: 60px;
        text-align: center;
    }

    .col-sticky {
        width: 50px;
        text-align: center;
    }

    .drag-handle {
        cursor: grab;
        color: #9ca3af;
        margin-right: 0.5rem;
    }

    .priority-number {
        color: #6b7280;
        font-size: 0.75rem;
    }

    .sticky-btn {
        background: none;
        border: none;
        cursor: pointer;
        font-size: 1rem;
        opacity: 0.5;
        transition: opacity 0.2s;
    }

    .sticky-btn:hover {
        opacity: 1;
    }

    .sticky-btn.is-sticky {
        opacity: 1;
    }

    .article-title {
        max-width: 300px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .article-title.clickable {
        cursor: pointer;
        color: #3b82f6;
    }

    .article-title.clickable:hover {
        text-decoration: underline;
    }

    .status-badge {
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 500;
    }

    .status-draft {
        background: #fef3c7;
        color: #92400e;
    }

    .status-editor {
        background: #dbeafe;
        color: #1e40af;
    }

    .status-published {
        background: #d1fae5;
        color: #065f46;
    }

    .reads-count, .rating-cell {
        text-align: center;
        font-size: 0.875rem;
        color: #6b7280;
    }

    .active-badge {
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 500;
    }

    .active-badge.active {
        background: #d1fae5;
        color: #065f46;
    }

    .active-badge.inactive-badge {
        background: #fee2e2;
        color: #991b1b;
    }

    .action-buttons {
        display: flex;
        gap: 0.5rem;
        flex-wrap: wrap;
    }

    .action-buttons button {
        padding: 0.25rem 0.5rem;
        border: none;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 500;
        cursor: pointer;
        transition: background 0.2s;
    }

    .recall-btn {
        background: #fef3c7;
        color: #92400e;
    }

    .recall-btn:hover {
        background: #fde68a;
    }

    .delete-btn {
        background: #fee2e2;
        color: #991b1b;
    }

    .delete-btn:hover {
        background: #fecaca;
    }

    .reactivate-btn {
        background: #d1fae5;
        color: #065f46;
    }

    .reactivate-btn:hover {
        background: #a7f3d0;
    }

    .purge-btn {
        background: #7f1d1d;
        color: white;
    }

    .purge-btn:hover {
        background: #991b1b;
    }

    /* Resources section */
    .resources-header {
        margin-bottom: 1rem;
    }

    .resources-editor-container {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 1rem;
    }

    /* Modal styles */
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
        max-width: 700px;
        max-height: 90vh;
        overflow-y: auto;
    }

    .modal h3 {
        margin: 0 0 0.5rem 0;
        color: #1a1a1a;
    }

    .modal-hint {
        color: #6b7280;
        font-size: 0.875rem;
        margin-bottom: 1.5rem;
    }

    .prompt-modal {
        width: 700px;
    }

    .prompt-edit-form {
        margin-bottom: 1.5rem;
    }

    .form-group {
        margin-bottom: 1rem;
    }

    .form-group label {
        display: block;
        font-weight: 500;
        margin-bottom: 0.5rem;
        color: #374151;
    }

    .form-group textarea {
        width: 100%;
        padding: 0.75rem;
        border: 1px solid #d1d5db;
        border-radius: 6px;
        font-family: monospace;
        font-size: 0.875rem;
        resize: vertical;
    }

    .modal-actions {
        display: flex;
        gap: 0.75rem;
        justify-content: flex-end;
    }

    .modal-actions button {
        padding: 0.5rem 1rem;
        border: 1px solid #d1d5db;
        border-radius: 6px;
        font-size: 0.875rem;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s;
        background: white;
        color: #374151;
    }

    .modal-actions button:hover {
        background: #f9fafb;
    }

    .modal-actions button.primary {
        background: #3b82f6;
        color: white;
        border-color: #3b82f6;
    }

    .modal-actions button.primary:hover {
        background: #2563eb;
    }

    .modal-actions button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .no-prompt {
        color: #6b7280;
        text-align: center;
        padding: 2rem;
    }
</style>
