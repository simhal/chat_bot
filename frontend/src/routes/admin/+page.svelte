<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { getAdminUsers, getAdminGroups, assignGroupToUser, removeGroupFromUser, createGroup, getUserInfo, getAdminArticles, deleteArticle, reactivateArticle, recallArticle, purgeArticle } from '$lib/api';
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';

    // Topic definitions
    const allTopics = [
        { id: 'macro', label: 'Macro' },
        { id: 'equity', label: 'Equity' },
        { id: 'fixed_income', label: 'Fixed Income' },
        { id: 'esg', label: 'ESG' }
    ];

    let users: any[] = [];
    let groups: any[] = [];
    let articles: any[] = [];
    let loading = true;
    let articlesLoading = false;
    let error = '';
    let selectedUserId: number | null = null;
    let selectedGroupNames: string[] = [];
    let selectedGroupForUsers: string | null = null;
    let selectedUserIds: number[] = [];
    let newGroupName = '';
    let newGroupDescription = '';

    // View state: 'topics' for topic tabs, 'users' for users view, 'groups' for groups view
    // Default to 'users' if global admin with no topic scopes, otherwise 'topics'
    let currentView: 'topics' | 'users' | 'groups' = 'topics';
    let selectedTopic: string = '';
    let initialViewSet = false;

    // Check permissions
    $: isGlobalAdmin = $auth.user?.scopes?.includes('global:admin') || false;

    // Topic tabs are only visible based on {topic}:admin scope, NOT global:admin
    $: adminTopics = allTopics.filter(topic => {
        if (!$auth.user?.scopes) return false;
        return $auth.user.scopes.includes(`${topic.id}:admin`);
    });

    $: hasAdminAccess = isGlobalAdmin || adminTopics.length > 0;

    // Redirect if no admin access
    $: if ($auth.isAuthenticated && !hasAdminAccess) {
        goto('/');
    }

    // Set default view and topic when permissions are loaded
    $: if (!initialViewSet && $auth.isAuthenticated) {
        if (adminTopics.length > 0) {
            currentView = 'topics';
            selectedTopic = adminTopics[0].id;
        } else if (isGlobalAdmin) {
            currentView = 'users';
        }
        initialViewSet = true;
    }

    async function loadData() {
        try {
            loading = true;
            error = '';
            if (isGlobalAdmin) {
                const [usersData, groupsData] = await Promise.all([
                    getAdminUsers(),
                    getAdminGroups()
                ]);
                users = usersData.sort((a: any, b: any) => a.email.localeCompare(b.email));
                groups = groupsData.sort((a: any, b: any) => a.name.localeCompare(b.name));
            }
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
            // getAdminArticles returns all articles for the topic
            const allArticles = await getAdminArticles(topic, 0, 100);
            articles = allArticles.sort((a: any, b: any) =>
                new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
            );
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to load articles';
            console.error('Error loading articles:', e);
        } finally {
            articlesLoading = false;
        }
    }

    $: if (selectedTopic && currentView === 'topics') {
        loadArticles(selectedTopic);
    }

    async function refreshCurrentUserIfNeeded(affectedUserId: number) {
        if ($auth.user?.id && parseInt($auth.user.id) === affectedUserId) {
            try {
                const updatedUserInfo = await getUserInfo();
                auth.updateUser(updatedUserInfo);
            } catch (e) {
                console.error('Failed to refresh current user info:', e);
            }
        }
    }

    async function handleAssignGroups() {
        if (!selectedUserId || selectedGroupNames.length === 0) return;
        const affectedUserId = selectedUserId;
        try {
            error = '';
            for (const groupName of selectedGroupNames) {
                await assignGroupToUser(selectedUserId, groupName);
            }
            await loadData();
            await refreshCurrentUserIfNeeded(affectedUserId);
            selectedUserId = null;
            selectedGroupNames = [];
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to assign groups';
        }
    }

    function toggleGroupSelection(groupName: string) {
        if (selectedGroupNames.includes(groupName)) {
            selectedGroupNames = selectedGroupNames.filter(name => name !== groupName);
        } else {
            selectedGroupNames = [...selectedGroupNames, groupName];
        }
    }

    async function handleAssignUsersToGroup() {
        if (!selectedGroupForUsers || selectedUserIds.length === 0) return;
        const affectedUserIds = [...selectedUserIds];
        try {
            error = '';
            for (const userId of selectedUserIds) {
                await assignGroupToUser(userId, selectedGroupForUsers);
            }
            await loadData();
            for (const userId of affectedUserIds) {
                await refreshCurrentUserIfNeeded(userId);
            }
            selectedGroupForUsers = null;
            selectedUserIds = [];
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to assign users to group';
        }
    }

    function toggleUserSelection(userId: number) {
        if (selectedUserIds.includes(userId)) {
            selectedUserIds = selectedUserIds.filter(id => id !== userId);
        } else {
            selectedUserIds = [...selectedUserIds, userId];
        }
    }

    async function handleRemoveGroup(userId: number, groupName: string) {
        if (!confirm(`Remove group "${groupName}" from this user?`)) return;
        try {
            error = '';
            await removeGroupFromUser(userId, groupName);
            await loadData();
            await refreshCurrentUserIfNeeded(userId);
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to remove group';
        }
    }

    async function handleCreateGroup() {
        if (!newGroupName.trim()) return;
        try {
            error = '';
            await createGroup(newGroupName.trim(), newGroupDescription.trim() || undefined);
            await loadData();
            newGroupName = '';
            newGroupDescription = '';
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to create group';
        }
    }

    async function handleDeleteArticle(articleId: number) {
        if (!confirm('Are you sure you want to deactivate this article?')) return;
        try {
            error = '';
            await deleteArticle(articleId);
            await loadArticles(selectedTopic);
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to deactivate article';
        }
    }

    async function handleReactivateArticle(articleId: number) {
        if (!confirm('Are you sure you want to reactivate this article?')) return;
        try {
            error = '';
            await reactivateArticle(articleId);
            await loadArticles(selectedTopic);
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to reactivate article';
        }
    }

    async function handleRecallArticle(articleId: number) {
        if (!confirm('Are you sure you want to recall this published article to draft?')) return;
        try {
            error = '';
            await recallArticle(articleId);
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

    onMount(() => {
        loadData();
    });
</script>

<div class="admin-container" class:topic-view={currentView === 'topics'}>
    <!-- Header with topic tabs and action buttons -->
    <div class="admin-header">
        <nav class="topic-tabs">
            {#each adminTopics as topic}
                <button
                    class="topic-tab"
                    class:active={currentView === 'topics' && selectedTopic === topic.id}
                    on:click={() => { currentView = 'topics'; selectedTopic = topic.id; }}
                >
                    {topic.label}
                </button>
            {/each}
        </nav>
        {#if isGlobalAdmin}
            <div class="admin-actions">
                <button
                    class="action-btn"
                    class:active={currentView === 'users'}
                    on:click={() => currentView = 'users'}
                >
                    Users
                </button>
                <button
                    class="action-btn"
                    class:active={currentView === 'groups'}
                    on:click={() => currentView = 'groups'}
                >
                    Groups
                </button>
            </div>
        {/if}
    </div>

    {#if error}
        <div class="error-message">{error}</div>
    {/if}

    {#if loading}
        <div class="loading">Loading...</div>
    {:else}
        <!-- Topic Articles View -->
        {#if currentView === 'topics' && selectedTopic}
            <section class="section">
                <h2>{allTopics.find(t => t.id === selectedTopic)?.label} Articles</h2>
                {#if articlesLoading}
                    <div class="loading">Loading articles...</div>
                {:else if articles.length === 0}
                    <p class="no-articles">No articles found for this topic.</p>
                {:else}
                    <div class="articles-table">
                        <table>
                            <thead>
                                <tr>
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
                                {#each articles as article}
                                    <tr class:inactive={!article.is_active}>
                                        <td class="article-title">{article.headline}</td>
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

        <!-- Users View -->
        {#if currentView === 'users'}
            <section class="section">
                <h2>Users ({users.length})</h2>
                <div class="users-table">
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Email</th>
                                <th>Name</th>
                                <th>Groups</th>
                                <th>Created</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each users as user}
                                <tr>
                                    <td>{user.id}</td>
                                    <td>{user.email}</td>
                                    <td>{user.name || '-'}</td>
                                    <td>
                                        <div class="groups-badges">
                                            {#each (user.groups || []).sort() as group}
                                                <span class="group-badge">
                                                    {group}
                                                    <button
                                                        class="remove-group"
                                                        on:click={() => handleRemoveGroup(user.id, group)}
                                                        title="Remove group"
                                                    >x</button>
                                                </span>
                                            {/each}
                                        </div>
                                    </td>
                                    <td>{new Date(user.created_at).toLocaleDateString()}</td>
                                    <td>
                                        <button
                                            class="assign-btn"
                                            on:click={() => selectedUserId = user.id}
                                        >
                                            Assign Group
                                        </button>
                                    </td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                </div>
            </section>
        {/if}

        <!-- Groups View -->
        {#if currentView === 'groups'}
            <section class="section">
                <h2>Groups</h2>
                <div class="groups-list">
                    {#each groups as group}
                        <div class="group-card">
                            <div class="group-card-header">
                                <div>
                                    <h3>{group.name}</h3>
                                    {#if group.description}
                                        <p>{group.description}</p>
                                    {/if}
                                    <span class="user-count">{group.user_count} users</span>
                                </div>
                                <button
                                    class="add-users-btn"
                                    on:click={() => selectedGroupForUsers = group.name}
                                >
                                    Add Users
                                </button>
                            </div>
                        </div>
                    {/each}
                </div>

                <div class="create-group">
                    <h3>Create New Group</h3>
                    <input
                        type="text"
                        bind:value={newGroupName}
                        placeholder="Group name"
                    />
                    <input
                        type="text"
                        bind:value={newGroupDescription}
                        placeholder="Description (optional)"
                    />
                    <button on:click={handleCreateGroup} disabled={!newGroupName.trim()}>
                        Create Group
                    </button>
                </div>
            </section>
        {/if}
    {/if}
</div>

<!-- Assign Groups to User Modal -->
{#if selectedUserId !== null}
    <div class="modal-overlay" on:click={() => { selectedUserId = null; selectedGroupNames = []; }}>
        <div class="modal" on:click|stopPropagation>
            <h3>Assign Groups to User</h3>
            <p class="modal-hint">Select one or more groups to assign</p>
            <div class="groups-checklist">
                {#each groups as group}
                    <label class="group-checkbox">
                        <input
                            type="checkbox"
                            checked={selectedGroupNames.includes(group.name)}
                            on:change={() => toggleGroupSelection(group.name)}
                        />
                        <span class="group-name">{group.name}</span>
                        {#if group.description}
                            <span class="group-desc">{group.description}</span>
                        {/if}
                    </label>
                {/each}
            </div>
            <div class="modal-actions">
                <button on:click={handleAssignGroups} disabled={selectedGroupNames.length === 0}>
                    Assign {selectedGroupNames.length > 0 ? `(${selectedGroupNames.length})` : ''}
                </button>
                <button on:click={() => { selectedUserId = null; selectedGroupNames = []; }}>Cancel</button>
            </div>
        </div>
    </div>
{/if}

<!-- Assign Users to Group Modal -->
{#if selectedGroupForUsers !== null}
    <div class="modal-overlay" on:click={() => { selectedGroupForUsers = null; selectedUserIds = []; }}>
        <div class="modal" on:click|stopPropagation>
            <h3>Add Users to {selectedGroupForUsers}</h3>
            <p class="modal-hint">Select one or more users to add to this group</p>
            <div class="groups-checklist">
                {#each users as user}
                    <label class="group-checkbox">
                        <input
                            type="checkbox"
                            checked={selectedUserIds.includes(user.id)}
                            on:change={() => toggleUserSelection(user.id)}
                        />
                        <div class="user-info-modal">
                            <span class="group-name">{user.email}</span>
                            {#if user.name}
                                <span class="group-desc">{user.name}</span>
                            {/if}
                            {#if user.groups && user.groups.length > 0}
                                <div class="user-groups-preview">
                                    Current groups: {user.groups.join(', ')}
                                </div>
                            {/if}
                        </div>
                    </label>
                {/each}
            </div>
            <div class="modal-actions">
                <button on:click={handleAssignUsersToGroup} disabled={selectedUserIds.length === 0}>
                    Add {selectedUserIds.length > 0 ? `(${selectedUserIds.length})` : ''}
                </button>
                <button on:click={() => { selectedGroupForUsers = null; selectedUserIds = []; }}>Cancel</button>
            </div>
        </div>
    </div>
{/if}

<style>
    :global(body) {
        background: #fafafa;
    }

    .admin-container {
        max-width: 1200px;
        margin: 0 auto;
        background: white;
        min-height: 100vh;
    }

    .admin-container.topic-view {
        max-width: 1800px;
    }

    .admin-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1px solid #e5e7eb;
        background: white;
        padding: 0 1rem;
    }

    .topic-tabs {
        display: flex;
        gap: 0;
    }

    .topic-tab {
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

    .topic-tab:hover {
        color: #1a1a1a;
        background: #f9fafb;
    }

    .topic-tab.active {
        color: #3b82f6;
        border-bottom-color: #3b82f6;
    }

    .admin-actions {
        display: flex;
        gap: 0.5rem;
    }

    .action-btn {
        padding: 0.5rem 1rem;
        background: #f3f4f6;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.875rem;
        font-weight: 500;
        color: #6b7280;
        transition: all 0.2s;
    }

    .action-btn:hover {
        background: #e5e7eb;
        color: #1a1a1a;
    }

    .action-btn.active {
        background: #3b82f6;
        color: white;
        border-color: #3b82f6;
    }

    .error-message {
        background: #ffebee;
        color: #d32f2f;
        padding: 1rem;
        border-radius: 4px;
        margin: 1rem;
    }

    .loading {
        text-align: center;
        padding: 2rem;
        color: #666;
    }

    .section {
        background: white;
        padding: 1.5rem;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        margin: 1rem;
    }

    .section h2 {
        margin-top: 0;
        color: #333;
        border-bottom: 2px solid #3b82f6;
        padding-bottom: 0.5rem;
    }

    .no-articles {
        color: #6b7280;
        text-align: center;
        padding: 2rem;
    }

    .articles-table, .users-table {
        overflow-x: auto;
    }

    table {
        width: 100%;
        border-collapse: collapse;
    }

    th, td {
        padding: 0.75rem;
        text-align: left;
        border-bottom: 1px solid #ddd;
    }

    th {
        background: #f5f5f5;
        font-weight: 600;
        color: #333;
    }

    tbody tr:hover {
        background: #f9f9f9;
    }

    tbody tr.inactive {
        opacity: 0.5;
        background: #f5f5f5;
    }

    .article-title {
        font-weight: 500;
        max-width: 300px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 12px;
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

    .active-badge {
        display: inline-block;
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 500;
    }

    .active-badge.active {
        background: #d1fae5;
        color: #065f46;
    }

    .inactive-badge {
        background: #fee2e2;
        color: #991b1b;
    }

    .delete-btn {
        padding: 0.4rem 0.75rem;
        background: #ef4444;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.75rem;
        font-weight: 500;
        transition: background 0.2s;
    }

    .delete-btn:hover {
        background: #dc2626;
    }

    .reactivate-btn {
        padding: 0.4rem 0.75rem;
        background: #10b981;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.75rem;
        font-weight: 500;
        transition: background 0.2s;
    }

    .reactivate-btn:hover {
        background: #059669;
    }

    .groups-badges {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
    }

    .group-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.25rem;
        padding: 0.25rem 0.5rem;
        background: #e3f2fd;
        color: #1976d2;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 500;
    }

    .remove-group {
        background: none;
        border: none;
        color: #d32f2f;
        font-size: 0.875rem;
        line-height: 1;
        cursor: pointer;
        padding: 0 0.25rem;
        margin-left: 0.25rem;
    }

    .remove-group:hover {
        color: #b71c1c;
    }

    .assign-btn {
        padding: 0.5rem 1rem;
        background: #4caf50;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.875rem;
    }

    .assign-btn:hover {
        background: #45a049;
    }

    .groups-list {
        display: flex;
        flex-direction: column;
        gap: 1rem;
        margin-bottom: 2rem;
    }

    .group-card {
        padding: 1rem;
        border: 1px solid #ddd;
        border-radius: 4px;
        background: #f9f9f9;
    }

    .group-card-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 1rem;
    }

    .group-card h3 {
        margin: 0 0 0.5rem 0;
        color: #3b82f6;
    }

    .group-card p {
        margin: 0 0 0.5rem 0;
        color: #666;
        font-size: 0.9rem;
    }

    .user-count {
        display: inline-block;
        padding: 0.25rem 0.5rem;
        background: #e3f2fd;
        color: #1976d2;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 500;
    }

    .add-users-btn {
        padding: 0.5rem 1rem;
        background: #4caf50;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.875rem;
        font-weight: 500;
        white-space: nowrap;
        transition: background 0.2s;
    }

    .add-users-btn:hover {
        background: #45a049;
    }

    .create-group {
        padding: 1rem;
        border: 2px dashed #ddd;
        border-radius: 4px;
    }

    .create-group h3 {
        margin-top: 0;
        font-size: 1rem;
    }

    .create-group input {
        width: 100%;
        padding: 0.5rem;
        margin-bottom: 0.5rem;
        border: 1px solid #ddd;
        border-radius: 4px;
        font-family: inherit;
    }

    .create-group button {
        width: 100%;
        padding: 0.5rem;
        background: #3b82f6;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-weight: 500;
    }

    .create-group button:hover:not(:disabled) {
        background: #2563eb;
    }

    .create-group button:disabled {
        background: #ccc;
        cursor: not-allowed;
    }

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
    }

    .modal {
        background: white;
        padding: 2rem;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);
        min-width: 400px;
    }

    .modal h3 {
        margin-top: 0;
        margin-bottom: 0.5rem;
    }

    .modal-hint {
        color: #6b7280;
        font-size: 0.875rem;
        margin: 0 0 1.5rem 0;
    }

    .groups-checklist {
        max-height: 400px;
        overflow-y: auto;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        padding: 0.5rem;
        margin-bottom: 1.5rem;
    }

    .group-checkbox {
        display: flex;
        align-items: flex-start;
        gap: 0.75rem;
        padding: 0.75rem;
        cursor: pointer;
        border-radius: 4px;
        transition: background 0.2s;
    }

    .group-checkbox:hover {
        background: #f9fafb;
    }

    .group-checkbox input[type="checkbox"] {
        margin-top: 0.25rem;
        cursor: pointer;
        width: 18px;
        height: 18px;
        flex-shrink: 0;
    }

    .group-checkbox .group-name {
        font-weight: 500;
        color: #1a1a1a;
        flex: 1;
    }

    .group-checkbox .group-desc {
        display: block;
        font-size: 0.875rem;
        color: #6b7280;
        margin-top: 0.25rem;
    }

    .user-info-modal {
        flex: 1;
    }

    .user-groups-preview {
        font-size: 0.75rem;
        color: #6b7280;
        margin-top: 0.5rem;
        font-style: italic;
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

    .reads-count {
        text-align: center;
        font-weight: 500;
        color: #6b7280;
    }

    .rating-cell {
        text-align: center;
        font-weight: 500;
        color: #f59e0b;
    }

    .action-buttons {
        display: flex;
        gap: 0.25rem;
        flex-wrap: nowrap;
        white-space: nowrap;
    }

    .recall-btn {
        padding: 0.4rem 0.75rem;
        background: #f59e0b;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.75rem;
        font-weight: 500;
        transition: background 0.2s;
    }

    .recall-btn:hover {
        background: #d97706;
    }

    .purge-btn {
        padding: 0.4rem 0.75rem;
        background: #7f1d1d;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.75rem;
        font-weight: 500;
        transition: background 0.2s;
    }

    .purge-btn:hover {
        background: #450a0a;
    }
</style>
