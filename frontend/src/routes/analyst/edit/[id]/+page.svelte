<script lang="ts">
    import { page } from '$app/stores';
    import { goto } from '$app/navigation';
    import { auth } from '$lib/stores/auth';
    import { getAnalystArticle, editArticle, chatWithContentAgent, submitArticleForReview, getArticleResources, getGlobalResources, getGroupResources, getResource, getResourceContentUrl, type Resource } from '$lib/api';
    import { onMount, onDestroy } from 'svelte';
    import Markdown from '$lib/components/Markdown.svelte';
    import ResourceEditor from '$lib/components/ResourceEditor.svelte';
    import { navigationContext, editorContentStore, type EditorContentPayload } from '$lib/stores/navigation';
    import { actionStore, type UIAction, type ActionResult } from '$lib/stores/actions';

    // Shared localStorage key for topic persistence
    const SELECTED_TOPIC_KEY = 'selected_topic';

    function getStoredTopic(): string | null {
        if (typeof localStorage !== 'undefined') {
            return localStorage.getItem(SELECTED_TOPIC_KEY);
        }
        return null;
    }

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

    interface ChatMessage {
        role: 'user' | 'agent';
        content: string;
        timestamp: Date;
    }

    let articleId: number;
    let article: Article | null = null;
    let loading = true;
    let error = '';
    let saving = false;

    // Editable fields
    let editHeadline = '';
    let editContent = '';
    let editKeywords = '';

    // Chat interface
    let chatMessages: ChatMessage[] = [];
    let chatInput = '';
    let chatLoading = false;

    // View mode: 'editor' | 'preview' | 'resources'
    let viewMode: 'editor' | 'preview' | 'resources' = 'preview';

    // Resources
    let resources: Resource[] = [];  // All resources linked to article
    let allTopicResources: Resource[] = [];  // All topic resources (for categorization)
    let allGlobalResources: Resource[] = [];  // All global resources (for categorization)
    let resourcesLoading = false;

    $: articleId = parseInt($page.params.id || '0');

    // Check if user can edit this topic
    function canEditTopic(topic: string): boolean {
        if (!$auth.user?.scopes) return false;

        // Check for admin, analyst, or editor role for the specific topic
        return $auth.user.scopes.includes(`${topic}:admin`) ||
               $auth.user.scopes.includes(`${topic}:analyst`) ||
               $auth.user.scopes.includes(`${topic}:editor`);
    }

    async function loadArticle() {
        try {
            loading = true;
            error = '';

            // Get stored topic from localStorage (set by analyst page)
            const storedTopic = getStoredTopic();
            if (!storedTopic) {
                error = 'Cannot determine article topic. Please navigate from the analyst page.';
                loading = false;
                return;
            }

            article = await getAnalystArticle(storedTopic, articleId);

            if (!article) {
                error = 'Article not found';
                return;
            }

            if (!canEditTopic(article.topic)) {
                error = 'You do not have permission to edit this article';
                return;
            }

            editHeadline = article.headline;
            editContent = article.content;
            editKeywords = article.keywords || '';

            // Update navigation context with article details for chat agent
            navigationContext.setContext({
                section: 'analyst',
                topic: article.topic,
                subNav: 'editing',
                articleId: article.id,
                articleHeadline: article.headline,
                articleKeywords: article.keywords || null,
                articleStatus: article.status || null,
                role: 'analyst'
            });

            // Load resources
            await loadResources();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to load article';
        } finally {
            loading = false;
        }
    }

    async function loadResources() {
        if (!articleId || !article) return;
        try {
            resourcesLoading = true;

            // Load article resources, topic resources, and global resources in parallel
            const [articleResponse, topicResponse, globalResponse] = await Promise.all([
                getArticleResources(articleId),
                getGroupResources(article.topic),
                getGlobalResources()
            ]);

            resources = articleResponse.resources;
            // Keep full lists for ResourceEditor to categorize linked resources
            allTopicResources = topicResponse.resources;
            allGlobalResources = globalResponse.resources;
        } catch (e) {
            console.error('Failed to load resources:', e);
        } finally {
            resourcesLoading = false;
        }
    }

    function handleResourceRefresh() {
        loadResources();
        // Switch to resources view to show the new resource
        viewMode = 'resources';
    }

    function handleResourceError(event: CustomEvent<string>) {
        error = event.detail;
    }

    function getStatusColor(status: string): string {
        switch (status) {
            case 'published': return '#10b981';
            case 'editor': return '#f59e0b';
            case 'draft':
            default: return '#6b7280';
        }
    }

    async function handleSubmit() {
        if (!article) return;
        try {
            // Save the article first before changing status
            saving = true;
            await editArticle(article.topic, article.id, editHeadline, editContent, editKeywords, article.status);
            saving = false;

            // Then submit to editor
            await submitArticleForReview(article.topic, article.id);
            goto(`/analyst/${article.topic}`);
        } catch (e) {
            saving = false;
            error = e instanceof Error ? e.message : 'Failed to submit article';
        }
    }

    async function handleSave() {
        if (!article) return;

        try {
            saving = true;
            error = '';
            await editArticle(article.topic, article.id, editHeadline, editContent, editKeywords, article.status);

            // Reload article to get updated data
            await loadArticle();

            // Show success message
            chatMessages = [...chatMessages, {
                role: 'agent',
                content: 'Article saved successfully.',
                timestamp: new Date()
            }];
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to save article';
        } finally {
            saving = false;
        }
    }

    async function handleChatSubmit() {
        if (!chatInput.trim() || !article) return;

        const userMessage = chatInput.trim();
        chatInput = '';

        // Add user message to chat
        chatMessages = [...chatMessages, {
            role: 'user',
            content: userMessage,
            timestamp: new Date()
        }];

        try {
            chatLoading = true;

            const response = await chatWithContentAgent(
                article.topic,
                article.id,
                userMessage,
                editHeadline,
                editContent,
                editKeywords
            );

            // Parse agent response
            try {
                // Try to extract JSON from the response
                const jsonMatch = response.response.match(/\{[\s\S]*\}/);
                if (jsonMatch) {
                    const agentData = JSON.parse(jsonMatch[0]);

                    // Update fields with agent's suggestions
                    if (agentData.headline) editHeadline = agentData.headline;
                    if (agentData.content) editContent = agentData.content;
                    if (agentData.keywords) editKeywords = agentData.keywords;

                    // Add agent response to chat
                    chatMessages = [...chatMessages, {
                        role: 'agent',
                        content: agentData.explanation || 'I\'ve updated the article based on your instructions.',
                        timestamp: new Date()
                    }];
                } else {
                    // If no JSON found, just show the response
                    chatMessages = [...chatMessages, {
                        role: 'agent',
                        content: response.response,
                        timestamp: new Date()
                    }];
                }
            } catch (parseError) {
                // If JSON parsing fails, show the raw response
                chatMessages = [...chatMessages, {
                    role: 'agent',
                    content: response.response,
                    timestamp: new Date()
                }];
            }
        } catch (e) {
            chatMessages = [...chatMessages, {
                role: 'agent',
                content: `Error: ${e instanceof Error ? e.message : 'Failed to communicate with agent'}`,
                timestamp: new Date()
            }];
        } finally {
            chatLoading = false;
        }
    }

    function formatTime(date: Date): string {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    // Convert table data to markdown table format
    function tableToMarkdown(name: string, columns: string[], data: any[][]): string {
        // Ensure we have at least one column
        if (!columns.length && !data.length) return `<!-- Empty table: ${name} -->`;

        // If no columns but data exists, create placeholder columns based on first row
        let finalColumns = columns;
        if (!columns.length && data.length > 0) {
            finalColumns = data[0].map((_, i) => `Column ${i + 1}`);
        }

        // Replace empty column headers with placeholder names
        finalColumns = finalColumns.map((col, i) => {
            const colStr = col != null ? String(col).trim() : '';
            return colStr === '' ? `Column ${i + 1}` : colStr;
        });

        if (!finalColumns.length) return `<!-- Empty table: ${name} -->`;

        const lines: string[] = [];

        // Add table caption as bold text
        lines.push(`**${name}**\n`);

        // Header row
        lines.push('| ' + finalColumns.map(col => String(col).replace(/\|/g, '\\|')).join(' | ') + ' |');

        // Separator row
        lines.push('| ' + finalColumns.map(() => '---').join(' | ') + ' |');

        // Data rows
        for (const row of data) {
            // Ensure row has same number of cells as columns
            const paddedRow = [...row];
            while (paddedRow.length < finalColumns.length) {
                paddedRow.push('');
            }
            const cells = paddedRow.slice(0, finalColumns.length).map(cell => {
                const val = cell != null ? String(cell) : '';
                return val.replace(/\|/g, '\\|').replace(/\n/g, ' ');
            });
            lines.push('| ' + cells.join(' | ') + ' |');
        }

        return lines.join('\n');
    }

    // Handle drop of resources onto the content textarea
    async function handleContentDrop(e: DragEvent) {
        e.preventDefault();

        const textarea = e.target as HTMLTextAreaElement;
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;

        // Check if it's a table resource (custom data type)
        const tableData = e.dataTransfer?.getData('application/x-table-resource');
        if (tableData) {
            try {
                const { hashId, name } = JSON.parse(tableData);
                // Fetch table data from API
                const contentUrl = getResourceContentUrl(hashId);
                const response = await fetch(contentUrl);
                if (response.ok) {
                    const tableJson = await response.json();
                    const columns = tableJson.columns || [];
                    const data = tableJson.data || [];

                    // Convert to markdown table
                    const markdownTable = tableToMarkdown(name, columns, data);

                    // Insert at cursor position
                    editContent = editContent.substring(0, start) + '\n' + markdownTable + '\n' + editContent.substring(end);

                    setTimeout(() => {
                        textarea.selectionStart = textarea.selectionEnd = start + markdownTable.length + 2;
                        textarea.focus();
                    }, 0);
                    return;
                }
            } catch (err) {
                console.error('Failed to fetch table data:', err);
            }
        }

        // Fallback to text/plain for other resources
        const text = e.dataTransfer?.getData('text/plain');
        if (!text) return;

        // Check if it's a markdown image link (![name](url)) or a resource link ([name](resource:hash_id))
        const isMarkdownImage = text.startsWith('![') && text.includes('](');
        const isResourceLink = text.startsWith('[') && text.includes('](resource:');

        if (isMarkdownImage || isResourceLink) {
            // Insert the markdown at cursor position
            editContent = editContent.substring(0, start) + '\n' + text + '\n' + editContent.substring(end);

            // Move cursor after the inserted text
            setTimeout(() => {
                textarea.selectionStart = textarea.selectionEnd = start + text.length + 2;
                textarea.focus();
            }, 0);
        }
    }

    // Allow drop on the textarea
    function handleContentDragOver(e: DragEvent) {
        e.preventDefault();
        if (e.dataTransfer) {
            e.dataTransfer.dropEffect = 'copy';
        }
    }

    // Subscribe to editor content from the main chat panel
    let editorContentUnsubscribe: (() => void) | null = null;
    let lastContentTimestamp = 0;

    function handleEditorContent(payload: EditorContentPayload | null) {
        if (!payload || payload.timestamp <= lastContentTimestamp) return;

        lastContentTimestamp = payload.timestamp;

        // Apply the content based on action
        if (payload.action === 'fill' || payload.action === 'replace') {
            if (payload.headline) editHeadline = payload.headline;
            if (payload.content) editContent = payload.content;
            if (payload.keywords) editKeywords = payload.keywords;
        } else if (payload.action === 'append') {
            if (payload.content) editContent += '\n\n' + payload.content;
        }

        // Check if new resources were linked
        const linkedResources = payload.linked_resources || [];
        const newlyLinked = linkedResources.filter(r => !r.already_linked);

        // Build message with resource info
        let message = 'Content has been generated and filled into the editor fields.';
        if (newlyLinked.length > 0) {
            message += `\n\n${newlyLinked.length} resource(s) have been linked to this article:`;
            for (const r of newlyLinked) {
                message += `\n• ${r.name} (${r.type})`;
            }
            message += '\n\nSwitching to Resources view...';
        }
        message += '\n\nPlease review and make any adjustments.';

        // Add a message to the local chat to indicate content was received
        chatMessages = [...chatMessages, {
            role: 'agent',
            content: message,
            timestamp: new Date()
        }];

        // If resources were linked, refresh the resources panel and switch to resources view
        if (newlyLinked.length > 0) {
            loadResources();
            viewMode = 'resources';
        }

        // Clear the store after consuming
        editorContentStore.clear();
    }

    // Action handlers for chat-triggered UI actions
    let actionUnsubscribers: (() => void)[] = [];

    async function handleSaveDraftAction(action: UIAction): Promise<ActionResult> {
        if (!article) {
            return { success: false, action: 'save_draft', error: 'No article loaded' };
        }
        try {
            await handleSave();
            return { success: true, action: 'save_draft', message: 'Article saved successfully' };
        } catch (e) {
            return { success: false, action: 'save_draft', error: e instanceof Error ? e.message : 'Failed to save' };
        }
    }

    async function handleSubmitForReviewAction(action: UIAction): Promise<ActionResult> {
        if (!article) {
            return { success: false, action: 'submit_for_review', error: 'No article loaded' };
        }
        try {
            // Save the article first before changing status
            saving = true;
            await editArticle(article.topic, article.id, editHeadline, editContent, editKeywords, article.status);
            saving = false;

            // Submit to editor (change status)
            await submitArticleForReview(article.topic, article.id);

            // Reload article to get updated status - stay on page, keep article focus
            await loadArticle();

            return { success: true, action: 'submit_for_review', message: `Article #${article.id} submitted for review` };
        } catch (e) {
            saving = false;
            return { success: false, action: 'submit_for_review', error: e instanceof Error ? e.message : 'Failed to submit' };
        }
    }

    async function handleSwitchViewEditorAction(action: UIAction): Promise<ActionResult> {
        viewMode = 'editor';
        return { success: true, action: 'switch_view_editor', message: 'Switched to editor view' };
    }

    async function handleSwitchViewPreviewAction(action: UIAction): Promise<ActionResult> {
        viewMode = 'preview';
        return { success: true, action: 'switch_view_preview', message: 'Switched to preview view' };
    }

    async function handleSwitchViewResourcesAction(action: UIAction): Promise<ActionResult> {
        viewMode = 'resources';
        await loadResources();
        return { success: true, action: 'switch_view_resources', message: 'Switched to resources view' };
    }

    async function handleOpenResourceModalAction(action: UIAction): Promise<ActionResult> {
        // Switch to resources view which shows the resource editor
        viewMode = 'resources';
        await loadResources();
        // The ResourceEditor component handles adding resources
        return { success: true, action: 'open_resource_modal', message: 'Resources panel opened' };
    }

    async function handleBrowseResourcesAction(action: UIAction): Promise<ActionResult> {
        viewMode = 'resources';
        await loadResources();
        return { success: true, action: 'browse_resources', message: 'Resources panel opened' };
    }

    async function handleArticleSubmittedAction(action: UIAction): Promise<ActionResult> {
        // Article was submitted - navigate back to analyst hub
        const articleTopic = article?.topic || getStoredTopic();
        await goto(articleTopic ? `/analyst/${articleTopic}` : '/analyst');
        return { success: true, action: 'article_submitted', message: 'Article submitted, returning to hub' };
    }

    onMount(() => {
        loadArticle();

        // Subscribe to editor content from the main chat
        editorContentUnsubscribe = editorContentStore.subscribe(handleEditorContent);

        // Register action handlers for this page
        actionUnsubscribers.push(
            actionStore.registerHandler('save_draft', handleSaveDraftAction),
            actionStore.registerHandler('submit_for_review', handleSubmitForReviewAction),
            actionStore.registerHandler('switch_view_editor', handleSwitchViewEditorAction),
            actionStore.registerHandler('switch_view_preview', handleSwitchViewPreviewAction),
            actionStore.registerHandler('switch_view_resources', handleSwitchViewResourcesAction),
            actionStore.registerHandler('open_resource_modal', handleOpenResourceModalAction),
            actionStore.registerHandler('browse_resources', handleBrowseResourcesAction),
            actionStore.registerHandler('article_submitted', handleArticleSubmittedAction)
        );
    });

    onDestroy(() => {
        if (editorContentUnsubscribe) {
            editorContentUnsubscribe();
        }
        // Unregister action handlers
        actionUnsubscribers.forEach(unsub => unsub());
    });
</script>

<div class="editor-container">
    {#if loading}
        <div class="loading-screen">
            <div class="spinner"></div>
            <p>Loading article...</p>
        </div>
    {:else if error && !article}
        <div class="error-screen">
            <h2>Error</h2>
            <p>{error}</p>
            <button on:click={() => goto('/')}>Back to Home</button>
        </div>
    {:else if article}
        <header class="editor-header">
            <div class="header-left">
                <button class="back-btn" on:click={() => article && goto(`/analyst/${article.topic}`)}>
                    ← Back to {article.topic.replace('_', ' ').toUpperCase()}
                </button>
                <div class="article-info">
                    <span class="article-id">Article #{article.id}</span>
                    <span class="article-status-badge" style="background-color: {getStatusColor(article.status)}">
                        {article.status}
                    </span>
                </div>
            </div>
            <div class="header-center">
                <div class="view-mode-buttons">
                    <button
                        class="view-btn"
                        class:active={viewMode === 'editor'}
                        on:click={() => viewMode = 'editor'}
                    >
                        Editor Only
                    </button>
                    <button
                        class="view-btn"
                        class:active={viewMode === 'preview'}
                        on:click={() => viewMode = 'preview'}
                    >
                        Editor / Preview
                    </button>
                    <button
                        class="view-btn"
                        class:active={viewMode === 'resources'}
                        on:click={() => viewMode = 'resources'}
                    >
                        Editor / Resources
                    </button>
                </div>
            </div>
            <div class="header-right">
                <button class="save-btn" on:click={handleSave} disabled={saving}>
                    {saving ? 'Saving...' : 'Save Changes'}
                </button>
                {#if article.status === 'draft'}
                    <button class="submit-btn" on:click={handleSubmit}>
                        Submit
                    </button>
                {/if}
            </div>
        </header>

        {#if error}
            <div class="error-banner">{error}</div>
        {/if}

        <div class="editor-main" class:single-panel={viewMode === 'editor'}>
            <!-- Editor Panel -->
            <div class="editor-panel">
                <div class="editor-content">
                    <div class="form-group">
                        <label for="headline">Headline</label>
                        <input
                            id="headline"
                            type="text"
                            bind:value={editHeadline}
                            placeholder="Article headline"
                            maxlength="500"
                        />
                    </div>

                    <div class="form-group">
                        <label for="keywords">Keywords (comma-separated)</label>
                        <input
                            id="keywords"
                            type="text"
                            bind:value={editKeywords}
                            placeholder="keyword1, keyword2, keyword3"
                            maxlength="500"
                        />
                    </div>

                    <div class="form-group flex-grow">
                        <label for="content">
                            Content (Markdown)
                            <span class="word-count">{editContent.split(/\s+/).filter(w => w.length > 0).length} words</span>
                        </label>
                        <textarea
                            id="content"
                            bind:value={editContent}
                            placeholder="Article content in Markdown format..."
                            on:drop={handleContentDrop}
                            on:dragover={handleContentDragOver}
                        ></textarea>
                    </div>
                </div>
            </div>

            <!-- Right Panel (Preview or Resources based on view mode) -->
            {#if viewMode === 'preview'}
                <div class="preview-panel">
                    <div class="preview-header">
                        <h3>Preview</h3>
                    </div>
                    <div class="preview-content">
                        <h1 class="preview-headline">{editHeadline || 'Untitled Article'}</h1>
                        {#if editKeywords}
                            <div class="preview-keywords">
                                {#each editKeywords.split(',') as keyword}
                                    <span class="keyword-tag">{keyword.trim()}</span>
                                {/each}
                            </div>
                        {/if}
                        <div class="preview-markdown">
                            <Markdown content={editContent} />
                        </div>
                    </div>
                </div>
            {:else if viewMode === 'resources'}
                <div class="resources-panel">
                    <div class="resources-header-bar">
                        <h3>Resources</h3>
                    </div>
                    <div class="resources-content">
                        <ResourceEditor
                            {resources}
                            topicResources={allTopicResources}
                            globalResources={allGlobalResources}
                            {articleId}
                            loading={resourcesLoading}
                            showDeleteButton={false}
                            showUnlinkButton={true}
                            on:refresh={handleResourceRefresh}
                            on:error={handleResourceError}
                        />
                    </div>
                </div>
            {/if}
        </div>

        <!-- Fixed Chat Panel -->
        <div class="chat-panel">
            <div class="chat-header">
                <h4>Content Agent Assistant</h4>
                <span class="chat-hint">Ask the agent to modify the article</span>
            </div>

            <div class="chat-messages">
                {#if chatMessages.length === 0}
                    <div class="chat-empty">
                        <p class="chat-welcome">Content Agent Assistant</p>
                        <p>Ask me to modify the article. For example:</p>
                        <ul>
                            <li>Improve the headline</li>
                            <li>Add more details to a section</li>
                            <li>Shorten or expand the content</li>
                            <li>Change the tone or style</li>
                            <li>Add relevant data or examples</li>
                        </ul>
                    </div>
                {:else}
                    {#each chatMessages as msg}
                        <div class="chat-message" class:user={msg.role === 'user'} class:agent={msg.role === 'agent'}>
                            <div class="message-header">
                                <span class="message-role">{msg.role === 'user' ? 'You' : 'Agent'}</span>
                                <span class="message-time">{formatTime(msg.timestamp)}</span>
                            </div>
                            <div class="message-content">{msg.content}</div>
                        </div>
                    {/each}
                {/if}
                {#if chatLoading}
                    <div class="chat-message agent loading">
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

            <form class="chat-input-form" on:submit|preventDefault={handleChatSubmit}>
                <input
                    type="text"
                    bind:value={chatInput}
                    placeholder="e.g., 'Make the introduction more engaging' or 'Add statistics about this topic'"
                    disabled={chatLoading}
                />
                <button type="submit" disabled={!chatInput.trim() || chatLoading}>
                    Send
                </button>
            </form>
        </div>
    {/if}
</div>

<style>
    .editor-container {
        display: flex;
        flex-direction: column;
        height: 100vh;
        background: #fafafa;
    }

    .loading-screen,
    .error-screen {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 100vh;
        gap: 1rem;
    }

    .spinner {
        width: 48px;
        height: 48px;
        border: 4px solid #f3f3f3;
        border-top: 4px solid #0077b5;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    .error-screen button {
        padding: 0.75rem 1.5rem;
        background: #0077b5;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-weight: 500;
    }

    .editor-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1rem 1.5rem;
        background: white;
        border-bottom: 1px solid #e5e7eb;
        gap: 1rem;
    }

    .header-left,
    .header-right {
        display: flex;
        align-items: center;
        gap: 1rem;
    }

    .header-center {
        display: flex;
        align-items: center;
    }

    .view-mode-buttons {
        display: flex;
        background: #f3f4f6;
        border-radius: 6px;
        padding: 3px;
        gap: 2px;
    }

    .view-btn {
        padding: 0.5rem 1rem;
        background: transparent;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.8rem;
        font-weight: 500;
        color: #6b7280;
        transition: all 0.2s;
        white-space: nowrap;
    }

    .view-btn:hover {
        color: #374151;
    }

    .view-btn.active {
        background: white;
        color: #1f2937;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
    }

    .back-btn {
        padding: 0.5rem 1rem;
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.875rem;
        transition: all 0.2s;
        color: #6b7280;
        font-weight: 500;
    }

    .back-btn:hover {
        background: #f9fafb;
        border-color: #d1d5db;
        color: #1a1a1a;
    }

    .article-info {
        display: flex;
        gap: 1rem;
        align-items: center;
    }

    .article-id {
        font-weight: 500;
        color: #6b7280;
        font-size: 0.875rem;
    }

    .article-status-badge {
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        color: white;
        text-transform: capitalize;
    }

    .save-btn {
        padding: 0.5rem 1.25rem;
        background: #3b82f6;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-weight: 500;
        font-size: 0.875rem;
        transition: all 0.2s;
    }

    .submit-btn {
        padding: 0.5rem 1rem;
        background: #10b981;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.875rem;
        font-weight: 500;
    }

    .submit-btn:hover {
        background: #059669;
    }

    .save-btn:hover:not(:disabled) {
        background: #2563eb;
    }

    .save-btn:disabled {
        background: #d1d5db;
        cursor: not-allowed;
    }

    .error-banner {
        padding: 1rem;
        background: #ffebee;
        color: #d32f2f;
        text-align: center;
        border-bottom: 1px solid #ffcdd2;
    }

    .editor-main {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 0;
        flex: 1;
        overflow: hidden;
        height: calc(100vh - 200px);
    }

    .editor-main.single-panel {
        grid-template-columns: 1fr;
    }

    .editor-panel,
    .preview-panel,
    .resources-panel {
        background: white;
        overflow-y: auto;
    }

    .editor-panel {
        border-right: 2px solid #e0e0e0;
    }

    .editor-content {
        padding: 1.5rem;
        display: flex;
        flex-direction: column;
        gap: 1rem;
        height: 100%;
    }

    .form-group {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
    }

    .form-group.flex-grow {
        flex: 1;
        min-height: 0;
    }

    .form-group label {
        font-weight: 600;
        color: #333;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .word-count {
        font-size: 0.85rem;
        color: #666;
        font-weight: normal;
    }

    .form-group input,
    .form-group select {
        padding: 0.75rem;
        border: 1px solid #e0e0e0;
        border-radius: 4px;
        font-size: 1rem;
        font-family: inherit;
    }

    .form-group textarea {
        flex: 1;
        padding: 1rem;
        border: 1px solid #e0e0e0;
        border-radius: 4px;
        font-size: 1rem;
        font-family: 'Courier New', monospace;
        line-height: 1.6;
        resize: none;
    }

    .form-group input:focus,
    .form-group textarea:focus,
    .form-group select:focus {
        outline: none;
        border-color: #0077b5;
        box-shadow: 0 0 0 2px rgba(0, 119, 181, 0.1);
    }

    .preview-panel {
        display: flex;
        flex-direction: column;
    }

    .preview-header {
        padding: 1rem 1.5rem;
        border-bottom: 1px solid #e0e0e0;
        background: #fafafa;
    }

    .preview-header h3 {
        margin: 0;
        color: #333;
        font-size: 1rem;
    }

    .preview-content {
        padding: 2rem;
        overflow-y: auto;
        flex: 1;
    }

    .preview-headline {
        margin: 0 0 1rem 0;
        color: #333;
        font-size: 2rem;
        line-height: 1.3;
    }

    .preview-keywords {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        margin-bottom: 1.5rem;
    }

    .keyword-tag {
        padding: 0.25rem 0.75rem;
        background: #e3f2fd;
        color: #0077b5;
        border-radius: 12px;
        font-size: 0.85rem;
    }

    .preview-markdown {
        line-height: 1.8;
        color: #333;
    }

    /* Resources Panel */
    .resources-panel {
        display: flex;
        flex-direction: column;
    }

    .resources-header-bar {
        padding: 1rem 1.5rem;
        border-bottom: 1px solid #e0e0e0;
        background: #fafafa;
    }

    .resources-header-bar h3 {
        margin: 0;
        color: #333;
        font-size: 1rem;
    }

    .resources-content {
        flex: 1;
        overflow-y: auto;
        padding: 1rem;
    }

    /* Chat Panel */
    .chat-panel {
        height: 200px;
        background: white;
        border-top: 2px solid #e0e0e0;
        display: flex;
        flex-direction: column;
    }

    .chat-header {
        padding: 0.75rem 1.5rem;
        background: #fafafa;
        border-bottom: 1px solid #e0e0e0;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .chat-header h4 {
        margin: 0;
        font-size: 0.95rem;
        color: #333;
    }

    .chat-hint {
        font-size: 0.85rem;
        color: #666;
    }

    .chat-messages {
        flex: 1;
        overflow-y: auto;
        padding: 1rem;
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
    }

    .chat-empty {
        color: #6b7280;
        font-size: 0.875rem;
        line-height: 1.6;
    }

    .chat-welcome {
        font-weight: 600;
        color: #1a1a1a;
        margin-bottom: 0.5rem;
    }

    .chat-empty ul {
        margin: 0.75rem 0 0 1.5rem;
        padding: 0;
    }

    .chat-empty li {
        margin: 0.375rem 0;
    }

    .chat-message {
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
        max-width: 80%;
    }

    .chat-message.user {
        align-self: flex-end;
    }

    .chat-message.agent {
        align-self: flex-start;
    }

    .message-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.75rem;
        color: #666;
        padding: 0 0.5rem;
    }

    .message-role {
        font-weight: 600;
    }

    .message-content {
        padding: 0.75rem;
        border-radius: 8px;
        font-size: 0.9rem;
        line-height: 1.5;
    }

    .chat-message.user .message-content {
        background: #3b82f6;
        color: white;
    }

    .chat-message.agent .message-content {
        background: #f9fafb;
        color: #1a1a1a;
        border: 1px solid #e5e7eb;
    }

    .typing-indicator {
        display: flex;
        gap: 0.25rem;
    }

    .typing-indicator span {
        width: 8px;
        height: 8px;
        background: #666;
        border-radius: 50%;
        animation: typing 1.4s infinite;
    }

    .typing-indicator span:nth-child(2) {
        animation-delay: 0.2s;
    }

    .typing-indicator span:nth-child(3) {
        animation-delay: 0.4s;
    }

    @keyframes typing {
        0%, 60%, 100% {
            transform: translateY(0);
            opacity: 0.7;
        }
        30% {
            transform: translateY(-10px);
            opacity: 1;
        }
    }

    .chat-input-form {
        display: flex;
        gap: 0.5rem;
        padding: 0.75rem 1rem;
        border-top: 1px solid #e0e0e0;
        background: white;
    }

    .chat-input-form input {
        flex: 1;
        padding: 0.75rem;
        border: 1px solid #e0e0e0;
        border-radius: 4px;
        font-size: 0.9rem;
        font-family: inherit;
    }

    .chat-input-form input:focus {
        outline: none;
        border-color: #0077b5;
        box-shadow: 0 0 0 2px rgba(0, 119, 181, 0.1);
    }

    .chat-input-form button {
        padding: 0.75rem 1.5rem;
        background: #3b82f6;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-weight: 500;
        font-size: 0.875rem;
        transition: all 0.2s;
    }

    .chat-input-form button:hover:not(:disabled) {
        background: #2563eb;
    }

    .chat-input-form button:disabled {
        background: #d1d5db;
        cursor: not-allowed;
    }
</style>
