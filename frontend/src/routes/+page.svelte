<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { sendChatMessage } from '$lib/api';
    import { PUBLIC_LINKEDIN_CLIENT_ID, PUBLIC_LINKEDIN_REDIRECT_URI } from '$env/static/public';

    let messages: Array<{ role: 'user' | 'assistant'; content: string }> = [];
    let inputMessage = '';
    let loading = false;
    let error = '';

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

    function handleLogout() {
        auth.logout();
        messages = [];
    }

    async function sendMessage() {
        if (!inputMessage.trim() || loading) return;

        const userMessage = inputMessage.trim();
        inputMessage = '';
        error = '';

        // Add user message to chat
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
</script>

<div class="app">
    <header>
        <h1>AI Chatbot</h1>
        {#if $auth.isAuthenticated}
            <div class="user-info">
                {#if $auth.user?.scopes?.includes('admin')}
                    <a href="/admin" class="admin-link">Admin</a>
                {/if}
                {#if $auth.user?.picture}
                    <img src={$auth.user.picture} alt="Profile" class="avatar" />
                {/if}
                <span>{$auth.user?.name || 'User'}</span>
                <button on:click={handleLogout} class="logout-btn">Logout</button>
            </div>
        {/if}
    </header>

    <main>
        {#if !$auth.isAuthenticated}
            <div class="login-container">
                <div class="login-card">
                    <h2>Welcome to AI Chatbot</h2>
                    <p>Please sign in with LinkedIn to start chatting</p>
                    <button on:click={initiateLinkedInLogin} class="linkedin-btn">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.32 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.79M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z"/>
                        </svg>
                        Sign in with LinkedIn
                    </button>
                </div>
            </div>
        {:else}
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
                                    {message.content}
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
                    {#if error}
                        <div class="error-message">{error}</div>
                    {/if}
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
        background: #f5f5f5;
    }

    header {
        background: white;
        padding: 1rem 2rem;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    header h1 {
        margin: 0;
        font-size: 1.5rem;
        color: #333;
    }

    .user-info {
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }

    .admin-link {
        padding: 0.5rem 1rem;
        background: #673ab7;
        color: white;
        text-decoration: none;
        border-radius: 4px;
        font-size: 0.875rem;
        font-weight: 500;
        transition: background 0.2s;
    }

    .admin-link:hover {
        background: #5e35b1;
    }

    .avatar {
        width: 32px;
        height: 32px;
        border-radius: 50%;
    }

    .logout-btn {
        padding: 0.5rem 1rem;
        background: #f44336;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.875rem;
    }

    .logout-btn:hover {
        background: #d32f2f;
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
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        text-align: center;
        max-width: 400px;
    }

    .login-card h2 {
        margin: 0 0 1rem;
        color: #333;
    }

    .login-card p {
        color: #666;
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

    .chat-container {
        display: flex;
        flex-direction: column;
        height: 100%;
        max-width: 900px;
        margin: 0 auto;
        background: white;
    }

    .messages {
        flex: 1;
        overflow-y: auto;
        padding: 2rem;
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }

    .empty-state {
        display: flex;
        justify-content: center;
        align-items: center;
        height: 100%;
        color: #999;
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
    }

    .message.user .message-content {
        background: #0077b5;
        color: white;
    }

    .message.assistant .message-content {
        background: #e9ecef;
        color: #333;
    }

    .typing-indicator {
        display: flex;
        gap: 4px;
    }

    .typing-indicator span {
        width: 8px;
        height: 8px;
        background: #666;
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
        border-top: 1px solid #e0e0e0;
        padding: 1rem;
    }

    .error-message {
        background: #ffebee;
        color: #d32f2f;
        padding: 0.5rem 1rem;
        border-radius: 4px;
        margin-bottom: 0.5rem;
        font-size: 0.875rem;
    }

    .input-wrapper {
        display: flex;
        gap: 0.5rem;
    }

    textarea {
        flex: 1;
        padding: 0.75rem;
        border: 1px solid #ddd;
        border-radius: 4px;
        font-family: inherit;
        font-size: 1rem;
        resize: none;
        min-height: 44px;
        max-height: 200px;
    }

    textarea:focus {
        outline: none;
        border-color: #0077b5;
    }

    textarea:disabled {
        background: #f5f5f5;
        cursor: not-allowed;
    }

    button {
        padding: 0.75rem 1.5rem;
        background: #0077b5;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 1rem;
        font-weight: 500;
    }

    button:hover:not(:disabled) {
        background: #006399;
    }

    button:disabled {
        background: #ccc;
        cursor: not-allowed;
    }
</style>
