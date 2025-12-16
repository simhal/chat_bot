<script lang="ts">
    import { page } from '$app/stores';
    import { goto } from '$app/navigation';
    import { auth } from '$lib/stores/auth';
    import { getArticle, editArticle, chatWithContentAgent } from '$lib/api';
    import { onMount } from 'svelte';
    import Markdown from '$lib/components/Markdown.svelte';

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

    // View mode
    let showPreview = true;

    $: articleId = parseInt($page.params.id);

    // Check if user can edit this topic
    function canEditTopic(topic: string): boolean {
        if (!$auth.user?.scopes) return false;

        // Check for specific analyst permission (admin doesn't get automatic access)
        const topicMap: Record<string, string> = {
            'macro': 'macro_analyst',
            'equity': 'equity_analyst',
            'fixed_income': 'fi_analyst',
            'esg': 'esg_analyst'
        };

        return $auth.user.scopes.includes(topicMap[topic]);
    }

    async function loadArticle() {
        try {
            loading = true;
            error = '';
            article = await getArticle(articleId);

            if (!canEditTopic(article.topic)) {
                error = 'You do not have permission to edit this article';
                return;
            }

            editHeadline = article.headline;
            editContent = article.content;
            editKeywords = article.keywords || '';
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to load article';
        } finally {
            loading = false;
        }
    }

    async function handleSave() {
        if (!article) return;

        try {
            saving = true;
            error = '';
            await editArticle(article.id, editHeadline, editContent, editKeywords);

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

    onMount(() => {
        loadArticle();
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
            <button on:click={() => goto('/admin/content')}>Back to Content Management</button>
        </div>
    {:else if article}
        <header class="editor-header">
            <div class="header-left">
                <button class="back-btn" on:click={() => goto(`/analyst/${article.topic}`)}>
                    ← Back to {article.topic.replace('_', ' ').toUpperCase()}
                </button>
                <div class="article-info">
                    <span class="article-id">Article #{article.id}</span>
                </div>
            </div>
            <div class="header-right">
                <button class="toggle-btn" on:click={() => showPreview = !showPreview}>
                    {showPreview ? 'Editor Only' : 'Show Preview'}
                </button>
                <button class="save-btn" on:click={handleSave} disabled={saving}>
                    {saving ? 'Saving...' : 'Save Changes'}
                </button>
            </div>
        </header>

        {#if error}
            <div class="error-banner">{error}</div>
        {/if}

        <div class="editor-main" class:preview-hidden={!showPreview}>
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
                        ></textarea>
                    </div>
                </div>
            </div>

            <!-- Preview Panel -->
            {#if showPreview}
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
    }

    .header-left,
    .header-right {
        display: flex;
        align-items: center;
        gap: 1rem;
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

    .toggle-btn {
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

    .toggle-btn:hover {
        background: #f9fafb;
        border-color: #d1d5db;
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
        height: calc(100vh - 200px); /* Header + chat panel */
    }

    .editor-main.preview-hidden {
        grid-template-columns: 1fr;
    }

    .editor-panel,
    .preview-panel {
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

    .form-group input {
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
    .form-group textarea:focus {
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
