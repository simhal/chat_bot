<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { getUserProfile, deleteUserAccount, getEntitledTopics, type Topic as TopicType } from '$lib/api';
    import { goto } from '$app/navigation';
    import { page } from '$app/stores';
    import { onMount } from 'svelte';

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

    // Topics loaded from database
    let dbTopics: TopicType[] = [];
    let topicsLoading = false;
    let topicsLoadedForUser: string | null = null; // Track which user we loaded topics for

    // Map database topics to the format used by navigation
    $: topics = dbTopics
        .filter(t => t.visible && t.active)
        .sort((a, b) => a.sort_order - b.sort_order)
        .map(t => ({ id: t.slug, label: t.title }));

    async function loadTopics() {
        if (topicsLoading) return; // Prevent concurrent loads
        try {
            topicsLoading = true;
            // Use entitled topics API - returns only topics user can access as reader
            // Backend filters by: active=true, visible=true, and user has explicit reader entitlement
            dbTopics = await getEntitledTopics('reader');
            topicsLoadedForUser = $auth.user?.email || 'authenticated';
        } catch (e) {
            console.error('Error loading topics:', e);
            dbTopics = [];
            topicsLoadedForUser = null; // Allow retry on error
        } finally {
            topicsLoading = false;
        }
    }

    // Load topics when auth state changes to authenticated
    // Use reactive statement to watch $auth.isAuthenticated
    $: {
        const currentUser = $auth.user?.email || ($auth.isAuthenticated ? 'authenticated' : null);
        if ($auth.isAuthenticated && currentUser !== topicsLoadedForUser && !topicsLoading) {
            loadTopics();
        } else if (!$auth.isAuthenticated) {
            // Clear topics when user logs out
            dbTopics = [];
            topicsLoadedForUser = null;
        }
    }

    // Check user access to topics
    function hasTopicAccess(topic: string): boolean {
        if (!$auth.user?.scopes) return false;
        if ($auth.user.scopes.includes('global:admin')) return true;
        return $auth.user.scopes.some(scope => scope.startsWith(`${topic}:`));
    }

    function hasAnalystAccess(topic: string): boolean {
        if (!$auth.user?.scopes) return false;
        if ($auth.user.scopes.includes('global:admin')) return true;
        return $auth.user.scopes.includes(`${topic}:analyst`);
    }

    function hasEditorAccess(topic: string): boolean {
        if (!$auth.user?.scopes) return false;
        if ($auth.user.scopes.includes('global:admin')) return true;
        // Only show for users with explicit editor role (not admin)
        return $auth.user.scopes.includes(`${topic}:editor`);
    }

    // Extract scopes for reactivity - this ensures Svelte tracks $auth.user.scopes as a dependency
    $: userScopes = $auth.user?.scopes || [];

    // Show all visible topics in navigation (already filtered to visible/active)
    $: accessibleTopics = topics;

    // Check if user has any analyst/editor access
    $: hasAnyAnalystAccess = userScopes.length >= 0 && topics.some(t => hasAnalystAccess(t.id));
    $: hasAnyEditorAccess = userScopes.length >= 0 && topics.some(t => hasEditorAccess(t.id));

    // Check if user has topic admin access (for any topic)
    function hasTopicAdminAccess(topic: string): boolean {
        if (!$auth.user?.scopes) return false;
        if ($auth.user.scopes.includes('global:admin')) return true;
        return $auth.user.scopes.includes(`${topic}:admin`);
    }
    $: hasAnyTopicAdminAccess = userScopes.length >= 0 && topics.some(t => hasTopicAdminAccess(t.id));

    // Check if user has global admin access
    $: isGlobalAdmin = userScopes.includes('global:admin');

    // Determine active route
    $: currentPath = $page.url.pathname;
    $: isHome = currentPath === '/';
    $: isAnalyst = currentPath.startsWith('/analyst');
    $: isEditor = currentPath.startsWith('/editor');
    $: isTopicAdmin = currentPath === '/admin' || (currentPath.startsWith('/admin') && !currentPath.startsWith('/root'));
    $: isGlobalAdminPage = currentPath.startsWith('/root');
    $: isProfile = currentPath.startsWith('/profile');
    // Get active topic from query param on home page
    $: activeTopic = isHome ? $page.url.searchParams.get('tab') : null;

    // Get user display name
    $: userFullName = $auth.user?.name && $auth.user?.surname
        ? `${$auth.user.name} ${$auth.user.surname}`
        : $auth.user?.name || $auth.user?.email || '';

    function handleLogout() {
        auth.logout();
        // Redirect to home page where the login button is displayed
        goto('/');
    }

    function navigateToProfile() {
        goto('/profile');
    }

    /**
     * Handle topic click with toggle behavior.
     * Clicking an already-active topic deselects it (navigates to search).
     */
    function handleTopicClick(event: MouseEvent, topicId: string) {
        if (activeTopic === topicId) {
            // Already active - toggle off (go to search view)
            event.preventDefault();
            goto('/reader/search');
        }
        // Otherwise, let the normal <a> navigation happen
    }

    function formatDate(dateString: string) {
        return new Date(dateString).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
    }
</script>

<header>
    {#if $auth.isAuthenticated}
        <nav class="header-nav">
            <!-- Topic tabs on the left (Chat removed - now always visible in split pane) -->
            <div class="topic-nav">
                <a href="/reader/search" class="nav-link topic-link" class:active={isHome && activeTopic === 'search'}>Search</a>
                {#each accessibleTopics as topic}
                    <a
                        href="/reader/{topic.id}"
                        class="nav-link topic-link"
                        class:active={isHome && activeTopic === topic.id}
                        on:click={(e) => handleTopicClick(e, topic.id)}
                    >{topic.label}</a>
                {/each}
            </div>

            <!-- Special function tabs aligned right -->
            <div class="function-nav">
                {#if hasAnyAnalystAccess}
                    <a href="/analyst" class="nav-link function-link" class:active={isAnalyst}>Analyst</a>
                {/if}
                {#if hasAnyEditorAccess}
                    <a href="/editor" class="nav-link function-link" class:active={isEditor}>Editor</a>
                {/if}
                {#if hasAnyTopicAdminAccess}
                    <a href="/admin" class="nav-link function-link" class:active={isTopicAdmin}>Topic Admin</a>
                {/if}
                {#if isGlobalAdmin}
                    <a href="/root" class="nav-link function-link" class:active={isGlobalAdminPage}>Global Admin</a>
                {/if}
                <a href="/profile" class="nav-link function-link" class:active={isProfile}>Profile</a>
            </div>
        </nav>
        <div class="user-info">
            {#if $auth.user?.picture}
                <img src={$auth.user.picture} alt="Profile" class="user-avatar" />
            {:else}
                <div class="user-avatar-placeholder">
                    {($auth.user?.name || $auth.user?.email || '?').charAt(0).toUpperCase()}
                </div>
            {/if}
            <span class="user-name">{userFullName}</span>
            <button on:click={handleLogout} class="logout-btn">Logout</button>
        </div>
    {/if}
</header>

<style>
    header {
        background: white;
        padding: 0.75rem 2rem;
        border-bottom: 1px solid #e5e7eb;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 1rem;
    }

    .header-nav {
        display: flex;
        gap: 0.5rem;
        align-items: center;
        flex: 1;
        justify-content: space-between;
    }

    .topic-nav {
        display: flex;
        gap: 0.5rem;
        align-items: center;
    }

    .function-nav {
        display: flex;
        gap: 0.5rem;
        align-items: center;
    }

    .nav-link {
        padding: 0.5rem 1rem;
        text-decoration: none;
        border-radius: 4px;
        font-size: 0.875rem;
        font-weight: 500;
        transition: all 0.2s;
        color: #6b7280;
        border: 1px solid #e5e7eb;
        background: white;
    }

    .nav-link:hover {
        background: #f9fafb;
        color: #1a1a1a;
        border-color: #d1d5db;
    }

    .nav-link.active {
        color: white;
        background: #3b82f6;
        border-color: #3b82f6;
        font-weight: 600;
        box-shadow: 0 2px 4px rgba(59, 130, 246, 0.3);
    }

    .nav-link.active:hover {
        background: #2563eb;
        border-color: #2563eb;
    }

    /* Function links have a different style */
    .function-link {
        background: #f9fafb;
    }

    .function-link.active {
        background: #6366f1;
        border-color: #6366f1;
        box-shadow: 0 2px 4px rgba(99, 102, 241, 0.3);
    }

    .function-link.active:hover {
        background: #4f46e5;
        border-color: #4f46e5;
    }

    .user-info {
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }

    .user-avatar {
        width: 32px;
        height: 32px;
        border-radius: 50%;
        object-fit: cover;
        border: 2px solid #e5e7eb;
    }

    .user-avatar-placeholder {
        width: 32px;
        height: 32px;
        border-radius: 50%;
        background: #3b82f6;
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.875rem;
        font-weight: 600;
        border: 2px solid #e5e7eb;
    }

    .user-name {
        font-size: 0.875rem;
        font-weight: 500;
        color: #374151;
        max-width: 150px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .profile-btn {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 1rem;
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.875rem;
        font-weight: 500;
        color: #1a1a1a;
        transition: all 0.2s;
    }

    .profile-btn:hover {
        background: #f9fafb;
        border-color: #d1d5db;
    }

    .avatar {
        width: 28px;
        height: 28px;
        border-radius: 50%;
    }

    .logout-btn {
        padding: 0.5rem 1rem;
        background: #ef4444;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.875rem;
        font-weight: 500;
        transition: background 0.2s;
    }

    .logout-btn:hover {
        background: #dc2626;
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
        padding: 0;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);
        min-width: 500px;
        max-width: 600px;
        max-height: 90vh;
        overflow-y: auto;
    }

    .modal-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1.5rem 2rem;
        border-bottom: 1px solid #e5e7eb;
        background: #f9fafb;
    }

    .modal-header h2 {
        margin: 0;
        color: #1a1a1a;
        font-size: 1.25rem;
        font-weight: 600;
    }

    .close-btn {
        background: none;
        border: none;
        font-size: 2rem;
        line-height: 1;
        cursor: pointer;
        color: #6b7280;
        padding: 0;
        width: 32px;
        height: 32px;
        transition: color 0.2s;
    }

    .close-btn:hover {
        color: #1a1a1a;
    }

    .profile-content {
        padding: 2rem;
    }

    .loading {
        text-align: center;
        padding: 3rem;
        color: #6b7280;
    }

    .error-message {
        background: #fef2f2;
        color: #dc2626;
        padding: 1rem;
        margin: 1rem 2rem;
        border-radius: 4px;
        border: 1px solid #fecaca;
    }

    .profile-section {
        margin-bottom: 2rem;
    }

    .profile-avatar-section {
        display: flex;
        justify-content: center;
        margin-bottom: 2rem;
    }

    .profile-avatar {
        width: 100px;
        height: 100px;
        border-radius: 50%;
        border: 3px solid #e5e7eb;
    }

    .profile-avatar-placeholder {
        width: 100px;
        height: 100px;
        border-radius: 50%;
        background: #3b82f6;
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 2.5rem;
        font-weight: 600;
        text-transform: uppercase;
    }

    .profile-info {
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }

    .info-row {
        display: flex;
        gap: 1rem;
        align-items: flex-start;
    }

    .info-label {
        font-weight: 600;
        color: #6b7280;
        min-width: 140px;
        font-size: 0.875rem;
    }

    .info-value {
        color: #1a1a1a;
        flex: 1;
        font-size: 0.875rem;
    }

    .groups-list {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
    }

    .group-badge {
        padding: 0.25rem 0.75rem;
        background: #eff6ff;
        color: #3b82f6;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 500;
    }

    .danger-zone {
        margin-top: 2rem;
        padding: 1.5rem;
        border: 2px solid #fecaca;
        border-radius: 8px;
        background: #fef2f2;
    }

    .danger-zone h3 {
        margin: 0 0 0.5rem 0;
        color: #dc2626;
        font-size: 1rem;
        font-weight: 600;
    }

    .danger-zone p {
        margin: 0 0 1rem 0;
        color: #991b1b;
        font-size: 0.875rem;
        line-height: 1.5;
    }

    .delete-account-btn {
        padding: 0.75rem 1.5rem;
        background: #dc2626;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-weight: 600;
        font-size: 0.875rem;
        transition: background 0.2s;
        width: 100%;
    }

    .delete-account-btn:hover {
        background: #991b1b;
    }
</style>
