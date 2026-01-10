<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/stores/auth';
	import { navigationContext, agentLabel, navigationDisplayInfo, getNavigationContextForAPI, editorContentStore } from '$lib/stores/navigation';
	import { actionStore, type UIAction } from '$lib/stores/actions';
	import { sendChatMessage, clearChatHistory, apiRequest, createEmptyArticle, type NavigationCommand, type EditorContent, type UIActionCommand, type ConfirmationPrompt } from '$lib/api';
	import Markdown from './Markdown.svelte';

	let messages: Array<{ role: 'user' | 'assistant'; content: string }> = $state([]);
	let inputMessage = $state('');
	let loading = $state(false);
	let clearing = $state(false);
	let error = $state('');
	let messagesContainer: HTMLDivElement;

	// HITL confirmation state
	let pendingConfirmation: ConfirmationPrompt | null = $state(null);
	let confirmationProcessing = $state(false);

	// Auto-scroll to bottom when new messages arrive
	async function scrollToBottom() {
		await tick();
		if (messagesContainer) {
			messagesContainer.scrollTop = messagesContainer.scrollHeight;
		}
	}

	$effect(() => {
		if (messages.length > 0) {
			scrollToBottom();
		}
	});

	/**
	 * Execute a navigation command from the chat agent.
	 */
	async function executeNavigation(navigation: NavigationCommand) {
		console.log('🧭 Executing navigation:', navigation);

		// Small delay to let the user see the response
		await new Promise((resolve) => setTimeout(resolve, 800));

		if (navigation.action === 'logout') {
			console.log('🚪 Logging out...');
			auth.logout();
			goto('/');
		} else if (navigation.action === 'navigate' && navigation.target) {
			console.log('➡️ Navigating to:', navigation.target);
			goto(navigation.target);
		} else {
			console.log('⚠️ Unknown navigation action or missing target:', navigation);
		}
	}

	/**
	 * Handle editor content from chat response (fills article editor fields).
	 * Uses the editorContentStore so the editor page can react to new content.
	 */
	function handleEditorContent(editorContent: EditorContent) {
		editorContentStore.setContent(editorContent);
	}

	/**
	 * Execute a UI action command from the chat agent.
	 * Dispatches the action to the actionStore for the appropriate page component to handle.
	 * Falls back to direct navigation for cross-page actions when no handler is registered.
	 */
	async function executeUIAction(uiAction: UIActionCommand) {
		console.log('🎯 Executing UI action:', uiAction);

		// Small delay to let the user see the response
		await new Promise((resolve) => setTimeout(resolve, 500));

		// Dispatch the action to the store - page components will handle it
		actionStore.dispatch({
			type: uiAction.type as UIAction['type'],
			params: uiAction.params
		});

		// Execute the action and wait for result
		const result = await actionStore.executeCurrentAction();
		if (result) {
			console.log('🎯 Action result:', result);

			// Handle fallback for navigation-related actions when no handler is registered
			if (!result.success && result.error?.includes('No handler available')) {
				const handled = await handleFallbackNavigation(uiAction);
				if (handled) {
					return; // Successfully handled via fallback
				}
			}

			// Show error feedback to the user
			if (!result.success && result.error) {
				error = result.error;
			}
		}
	}

	/**
	 * Handle HITL confirmation - user clicked Confirm button.
	 * Calls the API endpoint specified in the confirmation object.
	 */
	async function handleConfirm() {
		console.log('🔘 handleConfirm called, pendingConfirmation:', pendingConfirmation);
		if (!pendingConfirmation) {
			console.warn('⚠️ handleConfirm called but no pendingConfirmation');
			return;
		}

		const confirmation = pendingConfirmation;
		console.log('📋 Confirmation details:', {
			id: confirmation.id,
			type: confirmation.type,
			endpoint: confirmation.confirm_endpoint,
			method: confirmation.confirm_method,
			body: confirmation.confirm_body
		});
		pendingConfirmation = null;  // Clear the prompt immediately
		confirmationProcessing = true;

		// Add user's confirmation as a message
		const confirmMessage = confirmation.type === 'publish_approval' && confirmation.article_id
			? `Confirmed: Publish article #${confirmation.article_id}`
			: `Confirmed: ${confirmation.title}`;
		messages = [...messages, { role: 'user', content: confirmMessage }];
		loading = true;
		error = '';

		try {
			// Call the API endpoint specified in the confirmation
			if (confirmation.confirm_endpoint) {
				console.log('📤 Calling confirmation endpoint:', confirmation.confirm_endpoint);
				console.log('📤 Request options:', {
					method: confirmation.confirm_method || 'POST',
					hasBody: !!confirmation.confirm_body,
					body: confirmation.confirm_body
				});
				const result = await apiRequest(confirmation.confirm_endpoint, {
					method: confirmation.confirm_method || 'POST',
					body: confirmation.confirm_body ? JSON.stringify(confirmation.confirm_body) : undefined
				});

				console.log('✅ Confirmation API response:', result);

				// Show success message
				const successMessage = result.message || `${confirmation.title} completed successfully!`;
				messages = [...messages, { role: 'assistant', content: successMessage }];
			} else {
				// Fallback: send as chat message if no endpoint specified
				const navContext = getNavigationContextForAPI($navigationContext);
				const response = await sendChatMessage(confirmMessage, navContext);
				console.log('✅ Confirmation response:', response);
				messages = [...messages, { role: 'assistant', content: response.response }];

				if (response.ui_action) {
					await executeUIAction(response.ui_action);
				}
				if (response.navigation) {
					await executeNavigation(response.navigation);
				}
			}
		} catch (e) {
			console.error('❌ Confirmation failed:', e);
			console.error('❌ Error details:', {
				name: e instanceof Error ? e.name : 'Unknown',
				message: e instanceof Error ? e.message : String(e),
				stack: e instanceof Error ? e.stack : undefined
			});
			error = e instanceof Error ? e.message : 'Confirmation failed';
			messages = [...messages, { role: 'assistant', content: `Action failed: ${error}` }];
		} finally {
			loading = false;
			confirmationProcessing = false;
		}
	}

	/**
	 * Handle HITL cancellation - user clicked Cancel button.
	 * Sends a message to the chatbot to acknowledge the cancellation.
	 */
	async function handleCancel() {
		if (!pendingConfirmation) return;

		const confirmation = pendingConfirmation;
		pendingConfirmation = null;  // Clear the prompt immediately

		// Build a cancellation message
		let cancelMessage = '';
		if (confirmation.type === 'publish_approval' && confirmation.article_id) {
			cancelMessage = `Cancel publishing article #${confirmation.article_id}`;
		} else {
			cancelMessage = `Cancel: ${confirmation.title}`;
		}

		// Add user's cancellation as a message
		messages = [...messages, { role: 'user', content: cancelMessage }];
		loading = true;

		try {
			const navContext = getNavigationContextForAPI($navigationContext);
			const response = await sendChatMessage(cancelMessage, navContext);

			console.log('❌ Cancellation response:', response);
			messages = [...messages, { role: 'assistant', content: response.response }];
		} catch (e) {
			// Even if the cancel message fails, that's OK - action was cancelled
			messages = [...messages, { role: 'assistant', content: 'Action cancelled.' }];
		} finally {
			loading = false;
		}
	}

	/**
	 * Fallback handler for navigation-related UI actions when the target page isn't mounted.
	 * Returns true if the action was handled.
	 */
	async function handleFallbackNavigation(uiAction: UIActionCommand): Promise<boolean> {
		const articleId = uiAction.params?.article_id;
		const topic = uiAction.params?.topic;

		switch (uiAction.type) {
			case 'edit_article':
				if (articleId) {
					console.log('🧭 Fallback navigation: edit_article ->', articleId);
					goto(`/analyst/edit/${articleId}`);
					return true;
				}
				break;
			case 'view_article':
			case 'open_article':
				if (articleId) {
					console.log('🧭 Fallback navigation: view_article ->', articleId);
					// Navigate to home page with article context (will be handled by home page)
					goto(`/?article=${articleId}`);
					return true;
				}
				break;
			case 'select_topic':
				if (topic) {
					console.log('🧭 Fallback navigation: select_topic ->', topic);
					goto(`/analyst/${topic}`);
					return true;
				}
				break;
			case 'create_new_article':
				if (topic) {
					console.log('🧭 Fallback: create_new_article for topic ->', topic);
					try {
						// Create empty article via API, then navigate to editor
						const article = await createEmptyArticle(topic);
						goto(`/analyst/edit/${article.id}`);
						return true;
					} catch (e) {
						console.error('Failed to create article:', e);
						error = e instanceof Error ? e.message : 'Failed to create article';
					}
				}
				break;
			// Notification actions (article workflow completion)
			case 'article_submitted':
				console.log('🔔 Notification: article_submitted');
				// Navigate back to analyst hub
				goto(topic ? `/analyst/${topic}` : '/analyst');
				return true;
			case 'article_published':
				console.log('🔔 Notification: article_published');
				// Navigate to editor hub or home
				goto(topic ? `/editor/${topic}` : '/');
				return true;
			case 'article_rejected':
				console.log('🔔 Notification: article_rejected');
				// Navigate back to analyst hub to see the rejected article
				goto(topic ? `/analyst/${topic}` : '/analyst');
				return true;
			// Navigation actions (goto_*)
			case 'goto_home':
				console.log('🧭 Fallback navigation: goto_home ->', topic);
				goto(topic ? `/?tab=${topic}` : '/');
				return true;
			case 'goto_analyst':
				console.log('🧭 Fallback navigation: goto_analyst ->', topic);
				goto(topic ? `/analyst/${topic}` : '/analyst');
				return true;
			case 'goto_editor':
				console.log('🧭 Fallback navigation: goto_editor ->', topic);
				goto(topic ? `/editor/${topic}` : '/editor');
				return true;
			case 'goto_topic_admin':
				console.log('🧭 Fallback navigation: goto_topic_admin');
				goto('/admin');
				return true;
			case 'goto_admin_global':
				console.log('🧭 Fallback navigation: goto_admin_global');
				goto('/admin/global');
				return true;
			case 'goto_profile':
				console.log('🧭 Fallback navigation: goto_profile');
				goto('/profile');
				return true;
			case 'goto_search':
				console.log('🧭 Fallback navigation: goto_search ->', topic);
				// Navigate to home with search tab or trigger search modal
				goto(topic ? `/?tab=${topic}&search=true` : '/?search=true');
				return true;
		}
		return false;
	}

	async function sendMessage() {
		if (!inputMessage.trim() || loading) return;

		const userMessage = inputMessage.trim();
		inputMessage = '';
		error = '';

		messages = [...messages, { role: 'user', content: userMessage }];
		loading = true;

		try {
			// Include navigation context in the request
			const navContext = getNavigationContextForAPI($navigationContext);
			const response = await sendChatMessage(userMessage, navContext);
			console.log('📨 Chat response received:', {
				hasNavigation: !!response.navigation,
				navigation: response.navigation,
				hasEditorContent: !!response.editor_content,
				editorContent: response.editor_content,
				hasUIAction: !!response.ui_action,
				uiAction: response.ui_action,
				hasConfirmation: !!response.confirmation,
				confirmation: response.confirmation,
				hasArticleContext: !!response.article_context,
				articleContext: response.article_context,
				agentType: response.agent_type
			});
			messages = [...messages, { role: 'assistant', content: response.response }];

			// Handle HITL confirmation if present (show buttons for user decision)
			if (response.confirmation) {
				console.log('🔔 HITL Confirmation required:', response.confirmation);
				pendingConfirmation = response.confirmation;
			}

			// Handle editor content if present (fills article editor fields via store)
			if (response.editor_content) {
				console.log('✏️ Setting editor content via store:', response.editor_content);
				handleEditorContent(response.editor_content);
			}

			// Update navigation context with article info from backend validation
			if (response.article_context) {
				console.log('📝 Updating article context from backend:', response.article_context);
				navigationContext.setArticle(
					response.article_context.article_id,
					response.article_context.headline || null,
					response.article_context.keywords || null,
					response.article_context.status || null
				);
			}

			// Execute UI action command if present
			if (response.ui_action) {
				await executeUIAction(response.ui_action);
			}

			// Execute navigation command if present
			if (response.navigation) {
				await executeNavigation(response.navigation);
			}
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

	async function clearChat() {
		clearing = true;
		error = '';

		try {
			// Clear server-side chat memory in Redis
			await clearChatHistory();
			// Clear local messages
			messages = [];
		} catch (e) {
			console.error('Error clearing chat history:', e);
			// Still clear local messages even if server fails
			messages = [];
		} finally {
			clearing = false;
		}
	}
</script>

<div class="chat-panel">
	<!-- Context Bar -->
	<div class="context-bar">
		<div class="context-info">
			<span class="context-role role-{$navigationDisplayInfo.roleClass}">{$navigationDisplayInfo.role}</span>
			{#if $navigationDisplayInfo.topic}
				<span class="context-separator">•</span>
				<span class="context-topic">{$navigationDisplayInfo.topic}</span>
			{/if}
			<span class="context-separator">•</span>
			<span class="context-path">{$navigationDisplayInfo.path}</span>
			{#if $navigationContext.articleId}
				<span class="context-separator">•</span>
				<span class="context-article" title={$navigationContext.articleHeadline || ''}>
					<span class="article-badge">#{$navigationContext.articleId}</span>
					{#if $navigationContext.articleHeadline}
						<span class="article-title">{$navigationContext.articleHeadline.length > 25 ? $navigationContext.articleHeadline.substring(0, 25) + '...' : $navigationContext.articleHeadline}</span>
					{/if}
				</span>
			{/if}
		</div>
		{#if messages.length > 0}
			<button class="clear-btn" onclick={clearChat} disabled={clearing} title="Clear chat & memory">
				{#if clearing}
					<span class="clearing-spinner"></span>
				{:else}
					<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<path d="M3 6h18"></path>
						<path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path>
						<path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path>
					</svg>
				{/if}
			</button>
		{/if}
	</div>

	<!-- Agent Label Header -->
	<div class="agent-header">
		<div class="agent-label">
			<span class="agent-icon">🤖</span>
			<span class="agent-name">{$agentLabel}</span>
		</div>
	</div>

	<!-- Error Display -->
	{#if error}
		<div class="error-message">{error}</div>
	{/if}

	<!-- Messages Area -->
	<div class="messages" bind:this={messagesContainer}>
		{#if !$auth.isAuthenticated}
			<div class="empty-state">
				<p>Please log in to chat</p>
			</div>
		{:else if messages.length === 0}
			<div class="empty-state">
				<p>Ask me anything about your current view</p>
				<p class="hint">I'm aware of what you're looking at</p>
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
		{#if pendingConfirmation}
			<div class="confirmation-prompt">
				<div class="confirmation-header">
					<span class="confirmation-icon">⚠️</span>
					<span class="confirmation-title">{pendingConfirmation.title}</span>
				</div>
				<div class="confirmation-message">{pendingConfirmation.message}</div>
				<div class="confirmation-buttons">
					<button
						class="confirm-btn"
						onclick={handleConfirm}
						disabled={confirmationProcessing}
					>
						{#if confirmationProcessing}
							<span class="btn-spinner"></span>
						{:else}
							✓ {pendingConfirmation.confirm_label}
						{/if}
					</button>
					<button
						class="cancel-btn"
						onclick={handleCancel}
						disabled={confirmationProcessing}
					>
						✗ {pendingConfirmation.cancel_label}
					</button>
				</div>
			</div>
		{/if}
	</div>

	<!-- Input Area -->
	<div class="input-container">
		<div class="input-wrapper">
			<textarea
				bind:value={inputMessage}
				onkeypress={handleKeyPress}
				placeholder="Type your message..."
				rows="1"
				disabled={loading || !$auth.isAuthenticated}
			></textarea>
			<button
				class="send-btn"
				onclick={sendMessage}
				disabled={loading || !inputMessage.trim() || !$auth.isAuthenticated}
			>
				Send
			</button>
		</div>
	</div>
</div>

<style>
	.chat-panel {
		display: flex;
		flex-direction: column;
		height: 100%;
		background: white;
		overflow: hidden;
	}

	/* Context Bar */
	.context-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.375rem 0.75rem;
		background: #1e293b;
		border-bottom: 1px solid #334155;
		flex-shrink: 0;
	}

	.context-info {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.75rem;
		font-family: 'SF Mono', 'Consolas', monospace;
	}

	.context-role {
		padding: 0.125rem 0.5rem;
		border-radius: 3px;
		font-weight: 600;
		text-transform: uppercase;
		font-size: 0.65rem;
		letter-spacing: 0.5px;
	}

	.context-role.role-reader {
		background: #3b82f6;
		color: white;
	}

	.context-role.role-analyst {
		background: #8b5cf6;
		color: white;
	}

	.context-role.role-editor {
		background: #f59e0b;
		color: #1e293b;
	}

	.context-role.role-admin {
		background: #ef4444;
		color: white;
	}

	.context-separator {
		color: #64748b;
	}

	.context-topic {
		color: #94a3b8;
		font-weight: 500;
	}

	.context-path {
		color: #64748b;
	}

	.context-article {
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}

	.article-badge {
		background: #059669;
		color: white;
		padding: 0.0625rem 0.375rem;
		border-radius: 3px;
		font-size: 0.65rem;
		font-weight: 600;
	}

	.article-title {
		color: #94a3b8;
		font-size: 0.7rem;
		max-width: 200px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.clear-btn {
		padding: 0.25rem 0.375rem;
		background: transparent;
		border: 1px solid #475569;
		border-radius: 3px;
		color: #94a3b8;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.15s ease;
	}

	.clear-btn:hover:not(:disabled) {
		background: #7f1d1d;
		border-color: #ef4444;
		color: #fca5a5;
	}

	.clear-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.clearing-spinner {
		width: 12px;
		height: 12px;
		border: 2px solid #64748b;
		border-top-color: transparent;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	/* Agent Header */
	.agent-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.5rem 1rem;
		background: linear-gradient(to right, #f8fafc, #f1f5f9);
		border-bottom: 1px solid #e2e8f0;
		flex-shrink: 0;
	}

	.agent-label {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.875rem;
		font-weight: 500;
		color: #475569;
	}

	.agent-icon {
		font-size: 1rem;
	}

	.agent-name {
		color: #1e40af;
	}

	.error-message {
		padding: 0.5rem 1rem;
		background: #fef2f2;
		color: #dc2626;
		border-bottom: 1px solid #fecaca;
		font-size: 0.8rem;
		flex-shrink: 0;
	}

	.messages {
		flex: 1;
		overflow-y: auto;
		padding: 1rem;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		min-height: 0;
	}

	.empty-state {
		display: flex;
		flex-direction: column;
		justify-content: center;
		align-items: center;
		height: 100%;
		color: #9ca3af;
		text-align: center;
		padding: 1rem;
	}

	.empty-state p {
		margin: 0;
	}

	.empty-state .hint {
		font-size: 0.75rem;
		margin-top: 0.25rem;
		color: #d1d5db;
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
		max-width: 85%;
		padding: 0.5rem 0.75rem;
		border-radius: 8px;
		word-wrap: break-word;
		font-size: 0.875rem;
		line-height: 1.4;
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
		padding: 0.25rem 0;
	}

	.typing-indicator span {
		width: 6px;
		height: 6px;
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
		0%,
		60%,
		100% {
			transform: translateY(0);
		}
		30% {
			transform: translateY(-6px);
		}
	}

	.input-container {
		border-top: 1px solid #e5e7eb;
		padding: 0.75rem;
		background: white;
		flex-shrink: 0;
	}

	.input-wrapper {
		display: flex;
		gap: 0.5rem;
	}

	textarea {
		flex: 1;
		padding: 0.5rem 0.75rem;
		border: 1px solid #e5e7eb;
		border-radius: 4px;
		font-family: inherit;
		font-size: 0.875rem;
		resize: none;
		min-height: 36px;
		max-height: 100px;
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

	.send-btn {
		padding: 0.5rem 1rem;
		background: #3b82f6;
		color: white;
		border: none;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.8rem;
		font-weight: 500;
		transition: background 0.2s;
		white-space: nowrap;
	}

	.send-btn:hover:not(:disabled) {
		background: #2563eb;
	}

	.send-btn:disabled {
		background: #d1d5db;
		cursor: not-allowed;
	}

	/* Markdown content styling adjustments for compact view */
	.message-content :global(p) {
		margin: 0.25rem 0;
	}

	.message-content :global(p:first-child) {
		margin-top: 0;
	}

	.message-content :global(p:last-child) {
		margin-bottom: 0;
	}

	.message-content :global(pre) {
		font-size: 0.75rem;
		padding: 0.5rem;
		margin: 0.5rem 0;
	}

	.message-content :global(ul),
	.message-content :global(ol) {
		margin: 0.25rem 0;
		padding-left: 1.25rem;
	}

	/* HITL Confirmation Prompt */
	.confirmation-prompt {
		background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
		border: 1px solid #f59e0b;
		border-radius: 8px;
		padding: 0.875rem;
		margin-top: 0.5rem;
		box-shadow: 0 2px 8px rgba(245, 158, 11, 0.15);
	}

	.confirmation-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.5rem;
	}

	.confirmation-icon {
		font-size: 1.1rem;
	}

	.confirmation-title {
		font-weight: 600;
		font-size: 0.9rem;
		color: #92400e;
	}

	.confirmation-message {
		font-size: 0.8rem;
		color: #78350f;
		margin-bottom: 0.75rem;
		line-height: 1.4;
	}

	.confirmation-buttons {
		display: flex;
		gap: 0.5rem;
	}

	.confirm-btn {
		flex: 1;
		padding: 0.5rem 1rem;
		background: #059669;
		color: white;
		border: none;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.8rem;
		font-weight: 500;
		transition: background 0.2s;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.25rem;
	}

	.confirm-btn:hover:not(:disabled) {
		background: #047857;
	}

	.confirm-btn:disabled {
		background: #9ca3af;
		cursor: not-allowed;
	}

	.cancel-btn {
		flex: 1;
		padding: 0.5rem 1rem;
		background: #dc2626;
		color: white;
		border: none;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.8rem;
		font-weight: 500;
		transition: background 0.2s;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.25rem;
	}

	.cancel-btn:hover:not(:disabled) {
		background: #b91c1c;
	}

	.cancel-btn:disabled {
		background: #9ca3af;
		cursor: not-allowed;
	}

	.btn-spinner {
		width: 14px;
		height: 14px;
		border: 2px solid rgba(255, 255, 255, 0.3);
		border-top-color: white;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}
</style>
