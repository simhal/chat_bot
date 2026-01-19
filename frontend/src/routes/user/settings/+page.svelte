<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import {
		deleteUserAccount,
		getTonalities,
		getUserTonality,
		updateUserTonality,
		type TonalityOption,
		type TonalityPreferences
	} from '$lib/api';
	import { goto } from '$app/navigation';
	import { onMount, onDestroy } from 'svelte';
	import { browser } from '$app/environment';
	import { navigationContext, type SectionName } from '$lib/stores/navigation';
	import { actionStore, type UIAction, type ActionResult } from '$lib/stores/actions';

	let error = '';

	// Tonality settings
	let tonalities: TonalityOption[] = [];
	let userTonality: TonalityPreferences | null = null;
	let selectedChatTonality: number | null = null;
	let selectedContentTonality: number | null = null;
	let tonalityLoading = true;
	let tonalitySaving = false;

	// Redirect if not authenticated (only in browser)
	$: if (browser && !$auth.isAuthenticated) {
		goto('/');
	}

	async function loadTonalities() {
		try {
			tonalityLoading = true;
			const [tonalitiesData, userTonalityData] = await Promise.all([
				getTonalities(),
				getUserTonality()
			]);
			tonalities = tonalitiesData;
			userTonality = userTonalityData;
			selectedChatTonality = userTonalityData.chat_tonality?.id || null;
			selectedContentTonality = userTonalityData.content_tonality?.id || null;
		} catch (e) {
			console.error('Error loading tonalities:', e);
		} finally {
			tonalityLoading = false;
		}
	}

	async function saveTonalityPreferences() {
		try {
			tonalitySaving = true;
			error = '';
			await updateUserTonality(selectedChatTonality, selectedContentTonality);
			// Reload to confirm changes
			const updated = await getUserTonality();
			userTonality = updated;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to save tonality preferences';
		} finally {
			tonalitySaving = false;
		}
	}

	async function handleDeleteAccount() {
		if (
			!confirm(
				"Are you sure you want to delete your account? This action cannot be undone and will permanently delete:\n\n- Your user profile\n- All group memberships\n- Custom prompts\n- Agent interactions\n- Content ratings\n\nClick OK to confirm deletion."
			)
		) {
			return;
		}

		// Double confirmation
		if (
			!confirm(
				'This is your final warning. Are you absolutely sure you want to permanently delete your account?'
			)
		) {
			return;
		}

		try {
			error = '';
			await deleteUserAccount();
			auth.logout();
			goto('/');
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to delete account';
			console.error('Error deleting account:', e);
		}
	}

	// Action handlers for chat-triggered UI actions (from ui_actions.json)
	let actionUnsubscribers: (() => void)[] = [];

	async function handleSaveTonalityAction(action: UIAction): Promise<ActionResult> {
		try {
			// Allow optional params to set specific values
			if (action.params?.chat_tonality_id !== undefined) {
				selectedChatTonality = action.params.chat_tonality_id;
			}
			if (action.params?.content_tonality_id !== undefined) {
				selectedContentTonality = action.params.content_tonality_id;
			}
			await saveTonalityPreferences();
			return { success: true, action: 'save_tonality', message: 'Tonality preferences saved' };
		} catch (e) {
			return {
				success: false,
				action: 'save_tonality',
				error: e instanceof Error ? e.message : 'Failed to save'
			};
		}
	}

	async function handleDeleteAccountAction(action: UIAction): Promise<ActionResult> {
		if (!action.params?.confirmed) {
			return {
				success: false,
				action: 'delete_account',
				error: 'Action requires confirmation. Set confirmed=true to proceed.'
			};
		}
		try {
			await deleteUserAccount();
			auth.logout();
			goto('/');
			return { success: true, action: 'delete_account', message: 'Account deleted' };
		} catch (e) {
			return {
				success: false,
				action: 'delete_account',
				error: e instanceof Error ? e.message : 'Failed to delete account'
			};
		}
	}

	onMount(() => {
		// Set navigation context for user_settings section (from sections.json)
		navigationContext.setSection('user_settings' as SectionName);

		loadTonalities();

		// Register action handlers for this section (from sections.json ui_actions)
		actionUnsubscribers.push(
			actionStore.registerHandler('save_tonality', handleSaveTonalityAction),
			actionStore.registerHandler('delete_account', handleDeleteAccountAction)
		);
	});

	onDestroy(() => {
		actionUnsubscribers.forEach((unsub) => unsub());
	});
</script>

<div class="settings-container">
	<nav class="tabs">
		<a href="/user/profile" class="tab">Profile Info</a>
		<a href="/user/settings" class="tab active">Settings</a>
	</nav>

	{#if error}
		<div class="error-message">{error}</div>
	{/if}

	<div class="settings-content">
		<!-- Tonality Preferences -->
		<div class="settings-section" data-testid="tonality-settings">
			<h3>Response Style Preferences</h3>
			<p class="section-description">
				Choose the communication style for AI responses. This affects how the chatbot and content
				generator write their responses.
			</p>

			{#if tonalityLoading}
				<div class="loading-small">Loading tonality options...</div>
			{:else}
				<div class="tonality-form">
					<div class="form-group">
						<label for="chat-tonality">Chat Response Style</label>
						<select id="chat-tonality" bind:value={selectedChatTonality} data-testid="chat-tonality-select">
							<option value={null}>Default (Professional)</option>
							{#each tonalities as tonality}
								<option value={tonality.id}>
									{tonality.name}
									{tonality.is_default ? '(Default)' : ''}
								</option>
							{/each}
						</select>
						<span class="help-text">Style used for chat conversations</span>
					</div>

					<div class="form-group">
						<label for="content-tonality">Content Generation Style</label>
						<select id="content-tonality" bind:value={selectedContentTonality} data-testid="content-tonality-select">
							<option value={null}>Default (Professional)</option>
							{#each tonalities as tonality}
								<option value={tonality.id}>
									{tonality.name}
									{tonality.is_default ? '(Default)' : ''}
								</option>
							{/each}
						</select>
						<span class="help-text">Style used for article generation</span>
					</div>

					<button class="save-btn" on:click={saveTonalityPreferences} disabled={tonalitySaving} data-testid="save-preferences">
						{tonalitySaving ? 'Saving...' : 'Save Preferences'}
					</button>
				</div>
			{/if}
		</div>

		<!-- Danger Zone -->
		<div class="danger-zone">
			<h3>Danger Zone</h3>
			<p>
				Once you delete your account, there is no going back. This will permanently delete all your
				data.
			</p>
			<button class="delete-account-btn" on:click={handleDeleteAccount}>
				Delete My Account
			</button>
		</div>
	</div>
</div>

<style>
	:global(body) {
		background: #fafafa;
	}

	.settings-container {
		max-width: 1200px;
		margin: 0 auto;
		background: white;
		min-height: 100vh;
	}

	.tabs {
		display: flex;
		border-bottom: 1px solid #e5e7eb;
		background: white;
		margin-bottom: 2rem;
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
		text-decoration: none;
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
		margin-bottom: 1rem;
		border-radius: 4px;
		border: 1px solid #fecaca;
	}

	.settings-content {
		padding: 2rem 0;
	}

	.settings-section {
		background: white;
		border: 1px solid #e5e7eb;
		border-radius: 8px;
		padding: 1.5rem;
		margin-bottom: 1.5rem;
	}

	.settings-section h3 {
		margin: 0 0 0.5rem 0;
		color: #1a1a1a;
		font-size: 1.125rem;
	}

	.section-description {
		color: #6b7280;
		font-size: 0.875rem;
		margin-bottom: 1.5rem;
	}

	.loading-small {
		color: #6b7280;
		padding: 1rem 0;
	}

	.tonality-form {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		max-width: 400px;
	}

	.form-group {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.form-group label {
		font-weight: 500;
		color: #374151;
		font-size: 0.875rem;
	}

	.form-group select {
		padding: 0.625rem 0.75rem;
		border: 1px solid #d1d5db;
		border-radius: 6px;
		font-size: 0.875rem;
		background: white;
		cursor: pointer;
	}

	.form-group select:focus {
		outline: none;
		border-color: #3b82f6;
		box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
	}

	.help-text {
		font-size: 0.75rem;
		color: #9ca3af;
	}

	.save-btn {
		padding: 0.625rem 1.25rem;
		background: #3b82f6;
		color: white;
		border: none;
		border-radius: 6px;
		font-weight: 500;
		cursor: pointer;
		transition: background 0.2s;
		align-self: flex-start;
	}

	.save-btn:hover:not(:disabled) {
		background: #2563eb;
	}

	.save-btn:disabled {
		background: #93c5fd;
		cursor: not-allowed;
	}

	.danger-zone {
		background: #fef2f2;
		border: 1px solid #fecaca;
		border-radius: 8px;
		padding: 2rem;
		max-width: 600px;
	}

	.danger-zone h3 {
		color: #dc2626;
		margin: 0 0 1rem 0;
		font-size: 1.25rem;
	}

	.danger-zone p {
		color: #991b1b;
		margin-bottom: 1.5rem;
		line-height: 1.6;
	}

	.delete-account-btn {
		background: #dc2626;
		color: white;
		border: none;
		padding: 0.75rem 1.5rem;
		border-radius: 4px;
		font-weight: 500;
		cursor: pointer;
		transition: background 0.2s;
	}

	.delete-account-btn:hover {
		background: #b91c1c;
	}
</style>
