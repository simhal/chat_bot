<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { getUserProfile, deleteUserAccount, getTonalities, getUserTonality, updateUserTonality, type TonalityOption, type TonalityPreferences } from '$lib/api';
    import { goto } from '$app/navigation';
    import { onMount, onDestroy } from 'svelte';
    import { navigationContext } from '$lib/stores/navigation';
    import { actionStore, type UIAction, type ActionResult } from '$lib/stores/actions';

    // Set navigation context for profile section
    navigationContext.setContext({ section: 'profile', topic: null, subNav: null, articleId: null, articleHeadline: null, articleKeywords: null, articleStatus: null, role: 'reader', resourceId: null, resourceName: null, resourceType: null, viewMode: null });

    interface UserProfile {
        id: number;
        email: string;
        name: string | null;
        surname: string | null;
        picture: string | null;
        created_at: string;
        custom_prompt: string | null;
        groups: string[];
    }

    type ProfileTab = 'info' | 'settings';
    let currentTab: ProfileTab = 'info';

    const tabs = [
        { id: 'info' as ProfileTab, label: 'Profile Info' },
        { id: 'settings' as ProfileTab, label: 'Settings' }
    ];

    let userProfile: UserProfile | null = null;
    let loading = true;
    let error = '';

    // Tonality settings
    let tonalities: TonalityOption[] = [];
    let userTonality: TonalityPreferences | null = null;
    let selectedChatTonality: number | null = null;
    let selectedContentTonality: number | null = null;
    let tonalityLoading = false;
    let tonalitySaving = false;

    // Redirect if not authenticated
    $: if (!$auth.isAuthenticated) {
        goto('/');
    }

    async function loadUserProfile() {
        try {
            loading = true;
            error = '';
            userProfile = await getUserProfile();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to load profile';
            console.error('Error loading profile:', e);
        } finally {
            loading = false;
        }
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
        if (!confirm('Are you sure you want to delete your account? This action cannot be undone and will permanently delete:\n\n- Your user profile\n- All group memberships\n- Custom prompts\n- Agent interactions\n- Content ratings\n\nClick OK to confirm deletion.')) {
            return;
        }

        // Double confirmation
        if (!confirm('This is your final warning. Are you absolutely sure you want to permanently delete your account?')) {
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

    function formatDate(dateString: string) {
        return new Date(dateString).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
    }

    // Action handlers for chat-triggered UI actions
    let actionUnsubscribers: (() => void)[] = [];

    async function handleSwitchProfileTabAction(action: UIAction): Promise<ActionResult> {
        const tab = action.params?.tab;
        if (!tab) {
            return { success: false, action: 'switch_profile_tab', error: 'No tab specified' };
        }
        currentTab = tab as ProfileTab;
        // Update navigation context
        navigationContext.setSubNav(tab);
        return { success: true, action: 'switch_profile_tab', message: `Switched to ${tab} tab` };
    }

    async function handleSaveTonalityAction(action: UIAction): Promise<ActionResult> {
        try {
            await saveTonalityPreferences();
            return { success: true, action: 'save_tonality', message: 'Tonality preferences saved' };
        } catch (e) {
            return { success: false, action: 'save_tonality', error: e instanceof Error ? e.message : 'Failed to save' };
        }
    }

    async function handleDeleteAccountAction(action: UIAction): Promise<ActionResult> {
        if (!action.params?.confirmed) {
            return { success: false, action: 'delete_account', error: 'Action requires confirmation' };
        }
        try {
            await handleDeleteAccount();
            return { success: true, action: 'delete_account', message: 'Account deleted' };
        } catch (e) {
            return { success: false, action: 'delete_account', error: e instanceof Error ? e.message : 'Failed to delete account' };
        }
    }

    onMount(() => {
        loadUserProfile();
        loadTonalities();

        // Register action handlers for this page
        actionUnsubscribers.push(
            actionStore.registerHandler('switch_profile_tab', handleSwitchProfileTabAction),
            actionStore.registerHandler('save_tonality', handleSaveTonalityAction),
            actionStore.registerHandler('delete_account', handleDeleteAccountAction)
        );
    });

    onDestroy(() => {
        // Unregister action handlers
        actionUnsubscribers.forEach(unsub => unsub());
    });
</script>

<div class="profile-container">
    <!-- Tabs -->
    <nav class="tabs">
        {#each tabs as tab}
            <button
                class="tab"
                class:active={currentTab === tab.id}
                on:click={() => currentTab = tab.id}
            >
                {tab.label}
            </button>
        {/each}
    </nav>

    {#if error}
        <div class="error-message">{error}</div>
    {/if}

    {#if loading}
        <div class="loading">Loading profile...</div>
    {:else if userProfile}
        <!-- Profile Info Tab -->
        {#if currentTab === 'info'}
            <div class="profile-content">
                <div class="profile-section">
                    <div class="profile-avatar-section">
                        {#if userProfile.picture}
                            <img src={userProfile.picture} alt="Profile" class="profile-avatar" />
                        {:else}
                            <div class="profile-avatar-placeholder">
                                {userProfile.name?.charAt(0) || userProfile.email.charAt(0)}
                            </div>
                        {/if}
                    </div>

                    <div class="profile-info">
                        <div class="info-row">
                            <span class="info-label">Name:</span>
                            <span class="info-value">
                                {#if userProfile.name || userProfile.surname}
                                    {userProfile.name || ''} {userProfile.surname || ''}
                                {:else}
                                    Not set
                                {/if}
                            </span>
                        </div>

                        <div class="info-row">
                            <span class="info-label">Email:</span>
                            <span class="info-value">{userProfile.email}</span>
                        </div>

                        <div class="info-row">
                            <span class="info-label">Member Since:</span>
                            <span class="info-value">{formatDate(userProfile.created_at)}</span>
                        </div>

                        <div class="info-row">
                            <span class="info-label">Groups:</span>
                            <span class="info-value">
                                {#if userProfile.groups.length > 0}
                                    <div class="groups-list">
                                        {#each userProfile.groups as group}
                                            <span class="group-badge">{group}</span>
                                        {/each}
                                    </div>
                                {:else}
                                    No groups assigned
                                {/if}
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        {/if}

        <!-- Settings Tab -->
        {#if currentTab === 'settings'}
            <div class="settings-content">
                <!-- Tonality Preferences -->
                <div class="settings-section">
                    <h3>Response Style Preferences</h3>
                    <p class="section-description">Choose the communication style for AI responses. This affects how the chatbot and content generator write their responses.</p>

                    {#if tonalityLoading}
                        <div class="loading-small">Loading tonality options...</div>
                    {:else}
                        <div class="tonality-form">
                            <div class="form-group">
                                <label for="chat-tonality">Chat Response Style</label>
                                <select id="chat-tonality" bind:value={selectedChatTonality}>
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
                                <select id="content-tonality" bind:value={selectedContentTonality}>
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

                            <button
                                class="save-btn"
                                on:click={saveTonalityPreferences}
                                disabled={tonalitySaving}
                            >
                                {tonalitySaving ? 'Saving...' : 'Save Preferences'}
                            </button>
                        </div>
                    {/if}
                </div>

                <!-- Danger Zone -->
                <div class="danger-zone">
                    <h3>Danger Zone</h3>
                    <p>Once you delete your account, there is no going back. This will permanently delete all your data.</p>
                    <button class="delete-account-btn" on:click={handleDeleteAccount}>
                        Delete My Account
                    </button>
                </div>
            </div>
        {/if}
    {/if}
</div>

<style>
    :global(body) {
        background: #fafafa;
    }

    .profile-container {
        max-width: 1200px;
        margin: 0 auto;
        background: white;
        min-height: 100vh;
    }

    /* Tabs */
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

    .loading {
        text-align: center;
        padding: 3rem;
        color: #6b7280;
    }

    .profile-content, .settings-content {
        padding: 2rem 0;
    }

    .profile-section {
        background: white;
        border-radius: 8px;
        padding: 2rem;
        border: 1px solid #e5e7eb;
    }

    .profile-avatar-section {
        display: flex;
        justify-content: center;
        margin-bottom: 2rem;
    }

    .profile-avatar {
        width: 120px;
        height: 120px;
        border-radius: 50%;
        border: 3px solid #3b82f6;
    }

    .profile-avatar-placeholder {
        width: 120px;
        height: 120px;
        border-radius: 50%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 3rem;
        font-weight: 600;
        text-transform: uppercase;
    }

    .profile-info {
        max-width: 600px;
        margin: 0 auto;
    }

    .info-row {
        display: grid;
        grid-template-columns: 150px 1fr;
        gap: 1rem;
        padding: 1rem 0;
        border-bottom: 1px solid #f3f4f6;
    }

    .info-row:last-child {
        border-bottom: none;
    }

    .info-label {
        font-weight: 600;
        color: #374151;
    }

    .info-value {
        color: #6b7280;
    }

    .groups-list {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
    }

    .group-badge {
        background: #e0f2fe;
        color: #0369a1;
        padding: 0.25rem 0.75rem;
        border-radius: 12px;
        font-size: 0.875rem;
        font-weight: 500;
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

    /* Tonality Settings */
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
</style>
