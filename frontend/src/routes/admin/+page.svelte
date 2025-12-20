<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { getAdminUsers, getAdminGroups, assignGroupToUser, removeGroupFromUser, createGroup, createUser, banUser, unbanUser, deleteUser, getUserInfo, getAdminArticles, deleteArticle, reactivateArticle, recallArticle, purgeArticle, getPromptModules, getTonalities, updatePromptModule, createTonality, deleteTonality, setDefaultTonality, adminGetUserTonality, adminUpdateUserTonality, getGroupResources, getGlobalResources, deleteResource, createTextResource, type PromptModule, type TonalityOption, type TonalityPreferences, type Resource, type ResourceListResponse } from '$lib/api';
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import ResourceEditor from '$lib/components/ResourceEditor.svelte';

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

    // Create user modal state
    let showCreateUserModal = false;
    let newUserEmail = '';
    let newUserName = '';
    let newUserSurname = '';
    let createUserLoading = false;

    // Prompt management state
    let prompts: PromptModule[] = [];
    let promptsLoading = false;
    let editingPrompt: PromptModule | null = null;
    let editedTemplateText = '';
    let editedName = '';
    let editedDescription = '';
    let promptSaving = false;

    // New tonality form state
    let showNewTonalityForm = false;
    let newTonalityName = '';
    let newTonalityTemplate = '';
    let newTonalityDescription = '';
    let newTonalitySaving = false;

    // Topic-specific prompt editing
    let topicPrompt: PromptModule | null = null;
    let topicPromptLoading = false;
    let showTopicPromptModal = false;
    let topicPromptEdited = '';
    let topicPromptSaving = false;

    // User tonality management (admin)
    let availableTonalities: TonalityOption[] = [];
    let showUserTonalityModal = false;
    let userTonalityUserId: number | null = null;
    let userTonalityUserEmail = '';
    let userTonalityLoading = false;
    let userTonalitySaving = false;
    let selectedUserChatTonality: number | null = null;
    let selectedUserContentTonality: number | null = null;

    // Resource management state
    let resources: Resource[] = [];
    let resourcesLoading = false;
    let resourcesTotal = 0;
    let topicSubView: 'articles' | 'resources' = 'articles';
    let showCreateResourceModal = false;
    let newResourceName = '';
    let newResourceDescription = '';
    let newResourceContent = '';
    let newResourceType: 'text' | 'table' | 'timeseries' = 'text';
    let resourceSaving = false;

    // Prompt type labels
    const promptTypeLabels: Record<string, string> = {
        'general': 'General System Prompt',
        'chat_specific': 'Chat-Specific Prompt',
        'chat_constraint': 'Chat Constraint',
        'article_constraint': 'Article Constraint',
        'content_topic': 'Content Topic',
        'tonality': 'Tonality Style'
    };

    // Mandatory prompt types that cannot be deleted
    const mandatoryPromptTypes = ['general', 'chat_specific', 'chat_constraint', 'article_constraint'];

    // View state: 'topics' for topic tabs, 'users' for users view, 'groups' for groups view, 'prompts' for prompts, 'resources' for global resources
    // Default to 'users' if global admin with no topic scopes, otherwise 'topics'
    let currentView: 'topics' | 'users' | 'groups' | 'prompts' | 'resources' = 'topics';
    let selectedTopic: string = '';
    let initialViewSet = false;

    // Check permissions
    $: isGlobalAdmin = $auth.user?.scopes?.includes('global:admin') || false;

    // Topic tabs are visible based on {topic}:admin scope only
    // Global admins manage users/groups/prompts/resources, topic admins manage their topics
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

    $: if (selectedTopic && currentView === 'topics' && topicSubView === 'articles') {
        loadArticles(selectedTopic);
    }

    $: if (selectedTopic && currentView === 'topics' && topicSubView === 'resources') {
        loadTopicResources(selectedTopic);
    }

    $: if (currentView === 'resources') {
        loadGlobalResources();
    }

    // Get group ID for selected topic (for creating resources)
    // Groups are named {topic}:admin (e.g., "macro:admin")
    $: selectedTopicGroupId = groups.find(g => g.name === `${selectedTopic}:admin`)?.id;

    // Get group ID for global resources
    $: globalGroupId = groups.find(g => g.name === 'global')?.id;

    function handleTopicResourceRefresh() {
        if (selectedTopic) {
            loadTopicResources(selectedTopic);
        }
    }

    function handleGlobalResourceRefresh() {
        loadGlobalResources();
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

    async function loadGlobalResources() {
        try {
            resourcesLoading = true;
            error = '';
            const response = await getGlobalResources();
            resources = response.resources;
            resourcesTotal = response.total;
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to load global resources';
            console.error('Error loading global resources:', e);
        } finally {
            resourcesLoading = false;
        }
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

    async function handleCreateUser() {
        if (!newUserEmail.trim()) return;
        try {
            createUserLoading = true;
            error = '';
            await createUser(newUserEmail, newUserName || undefined, newUserSurname || undefined);
            await loadData();
            showCreateUserModal = false;
            newUserEmail = '';
            newUserName = '';
            newUserSurname = '';
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to create user';
        } finally {
            createUserLoading = false;
        }
    }

    async function handleBanUser(userId: number, email: string) {
        if (!confirm(`Ban user "${email}"? They will not be able to log in.`)) return;
        try {
            error = '';
            await banUser(userId);
            await loadData();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to ban user';
        }
    }

    async function handleUnbanUser(userId: number, email: string) {
        if (!confirm(`Unban user "${email}"?`)) return;
        try {
            error = '';
            await unbanUser(userId);
            await loadData();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to unban user';
        }
    }

    async function handleDeleteUser(userId: number, email: string) {
        if (!confirm(`Delete user "${email}"? This cannot be undone.`)) return;
        try {
            error = '';
            await deleteUser(userId);
            await loadData();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to delete user';
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

    async function handleDeleteResource(resourceId: number, resourceName: string) {
        if (!confirm(`Are you sure you want to delete the resource "${resourceName}"?`)) return;
        try {
            error = '';
            await deleteResource(resourceId);
            if (currentView === 'resources') {
                await loadGlobalResources();
            } else if (selectedTopic) {
                await loadTopicResources(selectedTopic);
            }
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to delete resource';
        }
    }

    function getResourceTypeLabel(type: string) {
        const labels: Record<string, string> = {
            'image': 'Image',
            'pdf': 'PDF',
            'text': 'Text',
            'excel': 'Excel',
            'zip': 'ZIP',
            'csv': 'CSV',
            'table': 'Table',
            'timeseries': 'Timeseries'
        };
        return labels[type] || type;
    }

    function getResourceTypeClass(type: string) {
        const classes: Record<string, string> = {
            'image': 'type-image',
            'pdf': 'type-pdf',
            'text': 'type-text',
            'excel': 'type-excel',
            'zip': 'type-zip',
            'csv': 'type-csv',
            'table': 'type-table',
            'timeseries': 'type-timeseries'
        };
        return classes[type] || '';
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

    // Prompt management functions
    async function loadPrompts() {
        try {
            promptsLoading = true;
            error = '';
            // Get all prompts (active_only=false to see everything)
            prompts = await getPromptModules();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to load prompts';
            console.error('Error loading prompts:', e);
        } finally {
            promptsLoading = false;
        }
    }

    function startEditingPrompt(prompt: PromptModule) {
        editingPrompt = prompt;
        editedTemplateText = prompt.template_text;
        editedName = prompt.name;
        editedDescription = prompt.description || '';
    }

    function cancelEditingPrompt() {
        editingPrompt = null;
        editedTemplateText = '';
        editedName = '';
        editedDescription = '';
    }

    async function savePromptChanges() {
        if (!editingPrompt) return;
        try {
            promptSaving = true;
            error = '';
            await updatePromptModule(
                editingPrompt.id,
                editedTemplateText,
                editedName !== editingPrompt.name ? editedName : undefined,
                editedDescription !== (editingPrompt.description || '') ? editedDescription : undefined
            );
            await loadPrompts();
            cancelEditingPrompt();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to save prompt';
        } finally {
            promptSaving = false;
        }
    }

    async function handleCreateTonality() {
        if (!newTonalityName.trim() || !newTonalityTemplate.trim()) return;
        try {
            newTonalitySaving = true;
            error = '';
            await createTonality(
                newTonalityName.trim(),
                newTonalityTemplate.trim(),
                newTonalityDescription.trim() || undefined
            );
            await loadPrompts();
            showNewTonalityForm = false;
            newTonalityName = '';
            newTonalityTemplate = '';
            newTonalityDescription = '';
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to create tonality';
        } finally {
            newTonalitySaving = false;
        }
    }

    async function handleDeleteTonality(moduleId: number, name: string) {
        if (!confirm(`Are you sure you want to delete the tonality "${name}"? This cannot be undone.`)) return;
        try {
            error = '';
            await deleteTonality(moduleId);
            await loadPrompts();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to delete tonality';
        }
    }

    async function handleSetDefaultTonality(moduleId: number) {
        if (!confirm('Set this tonality as the default? This will apply to all users who haven\'t selected a preference.')) return;
        try {
            error = '';
            await setDefaultTonality(moduleId);
            await loadPrompts();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to set default tonality';
        }
    }

    // Group prompts by type for display
    function getGroupedPrompts(promptList: PromptModule[]) {
        const grouped: Record<string, PromptModule[]> = {};
        for (const prompt of promptList) {
            const type = prompt.prompt_type;
            if (!grouped[type]) {
                grouped[type] = [];
            }
            grouped[type].push(prompt);
        }
        // Sort each group by sort_order
        for (const type of Object.keys(grouped)) {
            grouped[type].sort((a, b) => a.sort_order - b.sort_order);
        }
        return grouped;
    }

    $: groupedPrompts = getGroupedPrompts(prompts);

    // Load prompts when switching to prompts view
    $: if (currentView === 'prompts' && prompts.length === 0 && !promptsLoading) {
        loadPrompts();
    }

    // Topic-specific prompt functions
    async function loadTopicPrompt(topic: string) {
        try {
            topicPromptLoading = true;
            error = '';
            // Get all prompts and find the content_topic for this topic
            const allPrompts = await getPromptModules('content_topic', topic);
            topicPrompt = allPrompts.find((p: PromptModule) => p.prompt_type === 'content_topic' && p.prompt_group === topic) || null;
            if (topicPrompt) {
                topicPromptEdited = topicPrompt.template_text;
            }
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to load topic prompt';
            console.error('Error loading topic prompt:', e);
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

    function closeTopicPromptModal() {
        showTopicPromptModal = false;
        topicPrompt = null;
        topicPromptEdited = '';
    }

    async function saveTopicPrompt() {
        if (!topicPrompt) return;
        try {
            topicPromptSaving = true;
            error = '';
            await updatePromptModule(topicPrompt.id, topicPromptEdited);
            // Reload to verify
            await loadTopicPrompt(selectedTopic);
            closeTopicPromptModal();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to save topic prompt';
        } finally {
            topicPromptSaving = false;
        }
    }

    // Load available tonalities for user management
    async function loadAvailableTonalities() {
        try {
            availableTonalities = await getTonalities();
        } catch (e) {
            console.error('Failed to load tonalities:', e);
        }
    }

    // Open user tonality modal
    async function openUserTonalityModal(userId: number, userEmail: string) {
        userTonalityUserId = userId;
        userTonalityUserEmail = userEmail;
        showUserTonalityModal = true;
        userTonalityLoading = true;

        // Load tonalities if not already loaded
        if (availableTonalities.length === 0) {
            await loadAvailableTonalities();
        }

        // Load user's current tonality preferences
        try {
            const prefs = await adminGetUserTonality(userId);
            selectedUserChatTonality = prefs.chat_tonality?.id || null;
            selectedUserContentTonality = prefs.content_tonality?.id || null;
        } catch (e) {
            console.error('Failed to load user tonality:', e);
            selectedUserChatTonality = null;
            selectedUserContentTonality = null;
        } finally {
            userTonalityLoading = false;
        }
    }

    function closeUserTonalityModal() {
        showUserTonalityModal = false;
        userTonalityUserId = null;
        userTonalityUserEmail = '';
        selectedUserChatTonality = null;
        selectedUserContentTonality = null;
    }

    async function saveUserTonality() {
        if (!userTonalityUserId) return;
        try {
            userTonalitySaving = true;
            error = '';
            await adminUpdateUserTonality(userTonalityUserId, selectedUserChatTonality, selectedUserContentTonality);
            closeUserTonalityModal();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to save user tonality';
        } finally {
            userTonalitySaving = false;
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
                <button
                    class="action-btn"
                    class:active={currentView === 'prompts'}
                    on:click={() => currentView = 'prompts'}
                >
                    Prompts
                </button>
                <button
                    class="action-btn"
                    class:active={currentView === 'resources'}
                    on:click={() => currentView = 'resources'}
                >
                    Resources
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
        <!-- Topic View with Sub-tabs -->
        {#if currentView === 'topics' && selectedTopic}
            <section class="section">
                <div class="topic-section-header">
                    <div class="topic-sub-tabs">
                        <button
                            class="sub-tab"
                            class:active={topicSubView === 'articles'}
                            on:click={() => topicSubView = 'articles'}
                        >
                            Articles
                        </button>
                        <button
                            class="sub-tab"
                            class:active={topicSubView === 'resources'}
                            on:click={() => topicSubView = 'resources'}
                        >
                            Resources
                        </button>
                    </div>
                    {#if topicSubView === 'articles'}
                        <button
                            class="topic-prompt-btn"
                            on:click={openTopicPromptModal}
                        >
                            Edit Topic Prompt
                        </button>
                    {/if}
                </div>

                <!-- Articles Sub-View -->
                {#if topicSubView === 'articles'}
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
                {/if}

                <!-- Resources Sub-View -->
                {#if topicSubView === 'resources'}
                    <div class="resources-header">
                        <p class="resources-hint">Shared resources for {allTopics.find(t => t.id === selectedTopic)?.label} group. These resources can be linked to articles.</p>
                    </div>
                    <div class="resources-editor-container">
                        <ResourceEditor
                            {resources}
                            groupId={selectedTopicGroupId}
                            groupName={selectedTopic}
                            loading={resourcesLoading}
                            showDeleteButton={true}
                            showUnlinkButton={false}
                            on:refresh={handleTopicResourceRefresh}
                            on:error={handleResourceError}
                        />
                    </div>
                {/if}
            </section>
        {/if}

        <!-- Users View -->
        {#if currentView === 'users'}
            <section class="section">
                <div class="section-header">
                    <h2>Users ({users.length})</h2>
                    <button class="create-user-btn" on:click={() => showCreateUserModal = true}>
                        + Create User
                    </button>
                </div>
                <div class="users-table">
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Email</th>
                                <th>Name</th>
                                <th>Status</th>
                                <th>Groups</th>
                                <th>Last Access</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each users as user}
                                <tr class:banned={!user.active}>
                                    <td>{user.id}</td>
                                    <td>{user.email}</td>
                                    <td>{user.name || '-'} {user.surname || ''}</td>
                                    <td>
                                        <div class="status-badges">
                                            {#if !user.active}
                                                <span class="status-badge banned">Banned</span>
                                            {:else if user.is_pending}
                                                <span class="status-badge pending">Pending</span>
                                            {:else}
                                                <span class="status-badge active">Active</span>
                                            {/if}
                                        </div>
                                    </td>
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
                                    <td>{user.last_access_at ? new Date(user.last_access_at).toLocaleDateString() : 'Never'}</td>
                                    <td class="user-actions">
                                        <button
                                            class="assign-btn"
                                            on:click={() => selectedUserId = user.id}
                                        >
                                            Assign Group
                                        </button>
                                        <button
                                            class="tonality-btn"
                                            on:click={() => openUserTonalityModal(user.id, user.email)}
                                        >
                                            Tonality
                                        </button>
                                        {#if user.active}
                                            <button
                                                class="ban-btn"
                                                on:click={() => handleBanUser(user.id, user.email)}
                                            >
                                                Ban
                                            </button>
                                        {:else}
                                            <button
                                                class="unban-btn"
                                                on:click={() => handleUnbanUser(user.id, user.email)}
                                            >
                                                Unban
                                            </button>
                                        {/if}
                                        <button
                                            class="delete-user-btn"
                                            on:click={() => handleDeleteUser(user.id, user.email)}
                                        >
                                            Delete
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

        <!-- Prompts View -->
        {#if currentView === 'prompts'}
            <section class="section prompts-section">
                <div class="prompts-header">
                    <h2>Prompt Templates</h2>
                    <button
                        class="add-tonality-btn"
                        on:click={() => showNewTonalityForm = true}
                    >
                        + New Tonality
                    </button>
                </div>
                <p class="section-hint">Manage system prompts for the AI chatbot and content generation. Mandatory prompts cannot be deleted.</p>

                {#if promptsLoading}
                    <div class="loading">Loading prompts...</div>
                {:else}
                    <!-- System Prompts (non-tonality) -->
                    <div class="prompts-group">
                        <h3>System Prompts</h3>
                        <div class="prompts-list">
                            {#each Object.entries(groupedPrompts).filter(([type]) => type !== 'tonality') as [type, typePrompts]}
                                <div class="prompt-type-section">
                                    <h4>{promptTypeLabels[type] || type}</h4>
                                    {#each typePrompts as prompt}
                                        <div class="prompt-card">
                                            <div class="prompt-card-header">
                                                <div class="prompt-info">
                                                    <span class="prompt-name">{prompt.name}</span>
                                                    {#if prompt.prompt_group}
                                                        <span class="prompt-group-badge">{prompt.prompt_group}</span>
                                                    {/if}
                                                    {#if prompt.is_default}
                                                        <span class="default-badge">Default</span>
                                                    {/if}
                                                </div>
                                                <div class="prompt-actions">
                                                    <button
                                                        class="edit-prompt-btn"
                                                        on:click={() => startEditingPrompt(prompt)}
                                                    >
                                                        Edit
                                                    </button>
                                                </div>
                                            </div>
                                            {#if prompt.description}
                                                <p class="prompt-description">{prompt.description}</p>
                                            {/if}
                                            <div class="prompt-preview">
                                                {prompt.template_text.substring(0, 150)}{prompt.template_text.length > 150 ? '...' : ''}
                                            </div>
                                            <div class="prompt-meta">
                                                <span>Version {prompt.version}</span>
                                                {#if prompt.updated_at}
                                                    <span>Updated: {new Date(prompt.updated_at).toLocaleDateString()}</span>
                                                {/if}
                                            </div>
                                        </div>
                                    {/each}
                                </div>
                            {/each}
                        </div>
                    </div>

                    <!-- Tonality Prompts -->
                    {#if groupedPrompts['tonality'] && groupedPrompts['tonality'].length > 0}
                        <div class="prompts-group tonality-group">
                            <h3>Tonality Styles</h3>
                            <p class="tonality-hint">User-selectable communication styles for AI responses.</p>
                            <div class="tonality-list">
                                {#each groupedPrompts['tonality'] as prompt}
                                    <div class="tonality-card" class:is-default={prompt.is_default}>
                                        <div class="tonality-card-header">
                                            <div class="tonality-info">
                                                <span class="tonality-name">{prompt.name}</span>
                                                {#if prompt.is_default}
                                                    <span class="default-badge">Default</span>
                                                {/if}
                                            </div>
                                            <div class="tonality-actions">
                                                <button
                                                    class="edit-prompt-btn"
                                                    on:click={() => startEditingPrompt(prompt)}
                                                >
                                                    Edit
                                                </button>
                                                {#if !prompt.is_default}
                                                    <button
                                                        class="set-default-btn"
                                                        on:click={() => handleSetDefaultTonality(prompt.id)}
                                                    >
                                                        Set Default
                                                    </button>
                                                    <button
                                                        class="delete-tonality-btn"
                                                        on:click={() => handleDeleteTonality(prompt.id, prompt.name)}
                                                    >
                                                        Delete
                                                    </button>
                                                {/if}
                                            </div>
                                        </div>
                                        {#if prompt.description}
                                            <p class="tonality-description">{prompt.description}</p>
                                        {/if}
                                        <div class="tonality-preview">
                                            {prompt.template_text.substring(0, 100)}{prompt.template_text.length > 100 ? '...' : ''}
                                        </div>
                                    </div>
                                {/each}
                            </div>
                        </div>
                    {/if}
                {/if}
            </section>
        {/if}

        <!-- Global Resources View -->
        {#if currentView === 'resources'}
            <section class="section">
                <h2>Global Resources</h2>
                <p class="section-hint">Resources without a group. These are available globally and can be linked to any article.</p>

                <div class="resources-editor-container">
                    <ResourceEditor
                        {resources}
                        groupId={globalGroupId}
                        groupName="global"
                        loading={resourcesLoading}
                        showDeleteButton={true}
                        showUnlinkButton={false}
                        on:refresh={handleGlobalResourceRefresh}
                        on:error={handleResourceError}
                    />
                </div>
            </section>
        {/if}
    {/if}
</div>

<!-- Create User Modal -->
{#if showCreateUserModal}
    <div class="modal-overlay" on:click={() => showCreateUserModal = false}>
        <div class="modal" on:click|stopPropagation>
            <h3>Create New User</h3>
            <p class="modal-hint">Create a user before they log in via OAuth. They can be assigned groups immediately.</p>

            <div class="form-group">
                <label for="new-user-email">Email *</label>
                <input
                    id="new-user-email"
                    type="email"
                    bind:value={newUserEmail}
                    placeholder="user@example.com"
                    required
                />
            </div>

            <div class="form-group">
                <label for="new-user-name">First Name</label>
                <input
                    id="new-user-name"
                    type="text"
                    bind:value={newUserName}
                    placeholder="John"
                />
            </div>

            <div class="form-group">
                <label for="new-user-surname">Last Name</label>
                <input
                    id="new-user-surname"
                    type="text"
                    bind:value={newUserSurname}
                    placeholder="Doe"
                />
            </div>

            <p class="modal-note">
                The user will appear as "Pending" until they log in via LinkedIn OAuth.
                Their profile information will be updated from LinkedIn on first login.
            </p>

            <div class="modal-actions">
                <button
                    class="primary"
                    on:click={handleCreateUser}
                    disabled={!newUserEmail.trim() || createUserLoading}
                >
                    {createUserLoading ? 'Creating...' : 'Create User'}
                </button>
                <button on:click={() => showCreateUserModal = false}>Cancel</button>
            </div>
        </div>
    </div>
{/if}

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

<!-- Edit Prompt Modal -->
{#if editingPrompt !== null}
    <div class="modal-overlay" on:click={cancelEditingPrompt}>
        <div class="modal prompt-modal" on:click|stopPropagation>
            <h3>Edit Prompt: {editingPrompt.name}</h3>
            <p class="modal-hint">
                Type: {promptTypeLabels[editingPrompt.prompt_type] || editingPrompt.prompt_type}
                {#if editingPrompt.prompt_group}
                    | Group: {editingPrompt.prompt_group}
                {/if}
            </p>

            <div class="prompt-edit-form">
                <div class="form-group">
                    <label for="prompt-name">Name</label>
                    <input
                        type="text"
                        id="prompt-name"
                        bind:value={editedName}
                        placeholder="Prompt name"
                    />
                </div>

                <div class="form-group">
                    <label for="prompt-description">Description</label>
                    <input
                        type="text"
                        id="prompt-description"
                        bind:value={editedDescription}
                        placeholder="Optional description"
                    />
                </div>

                <div class="form-group">
                    <label for="prompt-template">Template Text</label>
                    <textarea
                        id="prompt-template"
                        bind:value={editedTemplateText}
                        rows="12"
                        placeholder="Enter the prompt template..."
                    ></textarea>
                </div>
            </div>

            <div class="modal-actions">
                <button
                    on:click={savePromptChanges}
                    disabled={promptSaving || !editedTemplateText.trim()}
                >
                    {promptSaving ? 'Saving...' : 'Save Changes'}
                </button>
                <button on:click={cancelEditingPrompt}>Cancel</button>
            </div>
        </div>
    </div>
{/if}

<!-- New Tonality Modal -->
{#if showNewTonalityForm}
    <div class="modal-overlay" on:click={() => showNewTonalityForm = false}>
        <div class="modal prompt-modal" on:click|stopPropagation>
            <h3>Create New Tonality</h3>
            <p class="modal-hint">Create a new communication style that users can select for AI responses.</p>

            <div class="prompt-edit-form">
                <div class="form-group">
                    <label for="tonality-name">Name *</label>
                    <input
                        type="text"
                        id="tonality-name"
                        bind:value={newTonalityName}
                        placeholder="e.g., Friendly, Formal, Technical"
                    />
                </div>

                <div class="form-group">
                    <label for="tonality-description">Description</label>
                    <input
                        type="text"
                        id="tonality-description"
                        bind:value={newTonalityDescription}
                        placeholder="Brief description of this style"
                    />
                </div>

                <div class="form-group">
                    <label for="tonality-template">Template Text *</label>
                    <textarea
                        id="tonality-template"
                        bind:value={newTonalityTemplate}
                        rows="8"
                        placeholder="Enter the tonality instructions...&#10;&#10;Example:&#10;Respond in a friendly and approachable manner. Use conversational language while maintaining professionalism."
                    ></textarea>
                </div>
            </div>

            <div class="modal-actions">
                <button
                    on:click={handleCreateTonality}
                    disabled={newTonalitySaving || !newTonalityName.trim() || !newTonalityTemplate.trim()}
                >
                    {newTonalitySaving ? 'Creating...' : 'Create Tonality'}
                </button>
                <button on:click={() => showNewTonalityForm = false}>Cancel</button>
            </div>
        </div>
    </div>
{/if}

<!-- Topic Prompt Modal -->
{#if showTopicPromptModal}
    <div class="modal-overlay" on:click={closeTopicPromptModal}>
        <div class="modal prompt-modal" on:click|stopPropagation>
            <h3>Edit {allTopics.find(t => t.id === selectedTopic)?.label} Topic Prompt</h3>
            <p class="modal-hint">
                This prompt is used when generating content for the {allTopics.find(t => t.id === selectedTopic)?.label} topic.
                It defines how the AI should approach content creation for this subject area.
            </p>

            {#if topicPromptLoading}
                <div class="loading">Loading topic prompt...</div>
            {:else if topicPrompt}
                <div class="prompt-edit-form">
                    <div class="form-group">
                        <label for="topic-prompt-template">Prompt Template</label>
                        <textarea
                            id="topic-prompt-template"
                            bind:value={topicPromptEdited}
                            rows="15"
                            placeholder="Enter the topic-specific prompt instructions..."
                        ></textarea>
                    </div>
                    <div class="prompt-meta">
                        <span>Version {topicPrompt.version}</span>
                        {#if topicPrompt.updated_at}
                            <span>Last updated: {new Date(topicPrompt.updated_at).toLocaleDateString()}</span>
                        {/if}
                    </div>
                </div>
            {:else}
                <p class="no-prompt-message">No topic prompt found for this topic. Please contact a global administrator.</p>
            {/if}

            <div class="modal-actions">
                {#if topicPrompt}
                    <button
                        on:click={saveTopicPrompt}
                        disabled={topicPromptSaving || !topicPromptEdited.trim()}
                    >
                        {topicPromptSaving ? 'Saving...' : 'Save Changes'}
                    </button>
                {/if}
                <button on:click={closeTopicPromptModal}>Cancel</button>
            </div>
        </div>
    </div>
{/if}

<!-- User Tonality Modal -->
{#if showUserTonalityModal}
    <div class="modal-overlay" on:click={closeUserTonalityModal}>
        <div class="modal" on:click|stopPropagation>
            <h3>Set Tonality Preferences</h3>
            <p class="modal-hint">Configure response style for: <strong>{userTonalityUserEmail}</strong></p>

            {#if userTonalityLoading}
                <div class="loading">Loading preferences...</div>
            {:else}
                <div class="tonality-form">
                    <div class="form-group">
                        <label for="user-chat-tonality">Chat Response Style</label>
                        <select id="user-chat-tonality" bind:value={selectedUserChatTonality}>
                            <option value={null}>Default (Professional)</option>
                            {#each availableTonalities as tonality}
                                <option value={tonality.id}>
                                    {tonality.name}
                                    {tonality.is_default ? '(System Default)' : ''}
                                </option>
                            {/each}
                        </select>
                        <span class="help-text">Style used for chat conversations</span>
                    </div>

                    <div class="form-group">
                        <label for="user-content-tonality">Content Generation Style</label>
                        <select id="user-content-tonality" bind:value={selectedUserContentTonality}>
                            <option value={null}>Default (Professional)</option>
                            {#each availableTonalities as tonality}
                                <option value={tonality.id}>
                                    {tonality.name}
                                    {tonality.is_default ? '(System Default)' : ''}
                                </option>
                            {/each}
                        </select>
                        <span class="help-text">Style used for article generation</span>
                    </div>
                </div>
            {/if}

            <div class="modal-actions">
                <button
                    on:click={saveUserTonality}
                    disabled={userTonalitySaving || userTonalityLoading}
                >
                    {userTonalitySaving ? 'Saving...' : 'Save Preferences'}
                </button>
                <button on:click={closeUserTonalityModal}>Cancel</button>
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

    /* Prompts View Styles */
    .prompts-section {
        max-width: 900px;
    }

    .prompts-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.5rem;
    }

    .prompts-header h2 {
        margin: 0;
        border-bottom: none;
        padding-bottom: 0;
    }

    .section-hint {
        color: #6b7280;
        font-size: 0.875rem;
        margin-bottom: 1.5rem;
    }

    .add-tonality-btn {
        padding: 0.5rem 1rem;
        background: #3b82f6;
        color: white;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        font-weight: 500;
        font-size: 0.875rem;
        transition: background 0.2s;
    }

    .add-tonality-btn:hover {
        background: #2563eb;
    }

    .prompts-group {
        margin-bottom: 2rem;
    }

    .prompts-group h3 {
        color: #374151;
        font-size: 1rem;
        font-weight: 600;
        margin: 0 0 1rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid #e5e7eb;
    }

    .prompt-type-section {
        margin-bottom: 1.5rem;
    }

    .prompt-type-section h4 {
        color: #6b7280;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin: 0 0 0.75rem 0;
    }

    .prompt-card {
        background: #f9fafb;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 0.75rem;
    }

    .prompt-card-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 0.5rem;
    }

    .prompt-info {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        flex-wrap: wrap;
    }

    .prompt-name {
        font-weight: 600;
        color: #1a1a1a;
    }

    .prompt-group-badge {
        background: #dbeafe;
        color: #1e40af;
        padding: 0.125rem 0.5rem;
        border-radius: 10px;
        font-size: 0.75rem;
        font-weight: 500;
    }

    .default-badge {
        background: #d1fae5;
        color: #065f46;
        padding: 0.125rem 0.5rem;
        border-radius: 10px;
        font-size: 0.75rem;
        font-weight: 500;
    }

    .prompt-actions {
        display: flex;
        gap: 0.5rem;
    }

    .edit-prompt-btn {
        padding: 0.375rem 0.75rem;
        background: #3b82f6;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.75rem;
        font-weight: 500;
        transition: background 0.2s;
    }

    .edit-prompt-btn:hover {
        background: #2563eb;
    }

    .prompt-description {
        color: #6b7280;
        font-size: 0.875rem;
        margin: 0 0 0.5rem 0;
    }

    .prompt-preview {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        padding: 0.75rem;
        font-family: monospace;
        font-size: 0.75rem;
        color: #374151;
        white-space: pre-wrap;
        word-break: break-word;
    }

    .prompt-meta {
        display: flex;
        gap: 1rem;
        margin-top: 0.5rem;
        font-size: 0.75rem;
        color: #9ca3af;
    }

    /* Tonality Styles */
    .tonality-group {
        background: #fefce8;
        border: 1px solid #fef08a;
        border-radius: 8px;
        padding: 1.5rem;
    }

    .tonality-hint {
        color: #854d0e;
        font-size: 0.875rem;
        margin: -0.5rem 0 1rem 0;
    }

    .tonality-list {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
        gap: 1rem;
    }

    .tonality-card {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 1rem;
    }

    .tonality-card.is-default {
        border-color: #10b981;
        box-shadow: 0 0 0 1px #10b981;
    }

    .tonality-card-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 0.5rem;
    }

    .tonality-info {
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .tonality-name {
        font-weight: 600;
        color: #1a1a1a;
    }

    .tonality-actions {
        display: flex;
        gap: 0.25rem;
    }

    .set-default-btn {
        padding: 0.25rem 0.5rem;
        background: #f3f4f6;
        color: #374151;
        border: 1px solid #d1d5db;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.7rem;
        font-weight: 500;
        transition: all 0.2s;
    }

    .set-default-btn:hover {
        background: #e5e7eb;
    }

    .delete-tonality-btn {
        padding: 0.25rem 0.5rem;
        background: #fee2e2;
        color: #991b1b;
        border: 1px solid #fecaca;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.7rem;
        font-weight: 500;
        transition: all 0.2s;
    }

    .delete-tonality-btn:hover {
        background: #fecaca;
    }

    .tonality-description {
        color: #6b7280;
        font-size: 0.813rem;
        margin: 0 0 0.5rem 0;
    }

    .tonality-preview {
        background: #f9fafb;
        border-radius: 4px;
        padding: 0.5rem;
        font-size: 0.75rem;
        color: #6b7280;
        font-style: italic;
    }

    /* Prompt Edit Modal */
    .prompt-modal {
        min-width: 600px;
        max-width: 800px;
    }

    .prompt-edit-form {
        margin-bottom: 1.5rem;
    }

    .prompt-edit-form .form-group {
        margin-bottom: 1rem;
    }

    .prompt-edit-form label {
        display: block;
        font-weight: 500;
        color: #374151;
        margin-bottom: 0.375rem;
        font-size: 0.875rem;
    }

    .prompt-edit-form input,
    .prompt-edit-form textarea {
        width: 100%;
        padding: 0.625rem 0.75rem;
        border: 1px solid #d1d5db;
        border-radius: 6px;
        font-size: 0.875rem;
        font-family: inherit;
        transition: border-color 0.2s;
    }

    .prompt-edit-form input:focus,
    .prompt-edit-form textarea:focus {
        outline: none;
        border-color: #3b82f6;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
    }

    .prompt-edit-form textarea {
        resize: vertical;
        min-height: 120px;
        font-family: monospace;
    }

    /* Topic Section Header */
    .topic-section-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1rem;
    }

    .topic-section-header h2 {
        margin: 0;
        border-bottom: none;
        padding-bottom: 0;
    }

    .topic-prompt-btn {
        padding: 0.5rem 1rem;
        background: #8b5cf6;
        color: white;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        font-weight: 500;
        font-size: 0.875rem;
        transition: background 0.2s;
    }

    .topic-prompt-btn:hover {
        background: #7c3aed;
    }

    .no-prompt-message {
        color: #6b7280;
        text-align: center;
        padding: 2rem;
        background: #f9fafb;
        border-radius: 8px;
    }

    /* User Actions Column */
    .user-actions {
        display: flex;
        gap: 0.5rem;
        flex-wrap: wrap;
    }

    .section-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1rem;
    }

    .section-header h2 {
        margin: 0;
    }

    .create-user-btn {
        padding: 0.5rem 1rem;
        background: #10b981;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.875rem;
        font-weight: 500;
        transition: background 0.2s;
    }

    .create-user-btn:hover {
        background: #059669;
    }

    .status-badges {
        display: flex;
        gap: 0.25rem;
    }

    .status-badge {
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 500;
    }

    .status-badge.active {
        background: #d1fae5;
        color: #059669;
    }

    .status-badge.pending {
        background: #fef3c7;
        color: #d97706;
    }

    .status-badge.banned {
        background: #fee2e2;
        color: #dc2626;
    }

    tr.banned {
        background: #fef2f2;
    }

    .ban-btn {
        padding: 0.375rem 0.75rem;
        background: #f59e0b;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.75rem;
        font-weight: 500;
        transition: background 0.2s;
    }

    .ban-btn:hover {
        background: #d97706;
    }

    .unban-btn {
        padding: 0.375rem 0.75rem;
        background: #10b981;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.75rem;
        font-weight: 500;
        transition: background 0.2s;
    }

    .unban-btn:hover {
        background: #059669;
    }

    .delete-user-btn {
        padding: 0.375rem 0.75rem;
        background: #dc2626;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.75rem;
        font-weight: 500;
        transition: background 0.2s;
    }

    .delete-user-btn:hover {
        background: #b91c1c;
    }

    .modal-note {
        font-size: 0.85rem;
        color: #6b7280;
        background: #f9fafb;
        padding: 0.75rem;
        border-radius: 4px;
        margin: 1rem 0;
    }

    .modal-actions button.primary {
        background: #3b82f6;
    }

    .modal-actions button.primary:hover {
        background: #2563eb;
    }

    .tonality-btn {
        padding: 0.5rem 1rem;
        background: #8b5cf6;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.875rem;
        font-weight: 500;
        transition: background 0.2s;
    }

    .tonality-btn:hover {
        background: #7c3aed;
    }

    /* Tonality Form */
    .tonality-form {
        display: flex;
        flex-direction: column;
        gap: 1.25rem;
        margin: 1.5rem 0;
    }

    .tonality-form .form-group {
        display: flex;
        flex-direction: column;
        gap: 0.375rem;
    }

    .tonality-form label {
        font-weight: 500;
        color: #374151;
        font-size: 0.875rem;
    }

    .tonality-form select {
        padding: 0.625rem 0.75rem;
        border: 1px solid #d1d5db;
        border-radius: 6px;
        font-size: 0.875rem;
        background: white;
        cursor: pointer;
    }

    .tonality-form select:focus {
        outline: none;
        border-color: #3b82f6;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
    }

    .tonality-form .help-text {
        font-size: 0.75rem;
        color: #9ca3af;
    }

    /* Topic Sub-Tabs */
    .topic-sub-tabs {
        display: flex;
        gap: 0;
        border-bottom: 2px solid #e5e7eb;
        margin-bottom: 1rem;
    }

    .sub-tab {
        padding: 0.75rem 1.25rem;
        background: none;
        border: none;
        border-bottom: 2px solid transparent;
        margin-bottom: -2px;
        cursor: pointer;
        font-size: 0.875rem;
        font-weight: 500;
        color: #6b7280;
        transition: all 0.2s;
    }

    .sub-tab:hover {
        color: #1a1a1a;
        background: #f9fafb;
    }

    .sub-tab.active {
        color: #3b82f6;
        border-bottom-color: #3b82f6;
    }

    /* Resources Styles */
    .resources-header {
        margin-bottom: 1rem;
    }

    .resources-hint {
        color: #6b7280;
        font-size: 0.875rem;
        margin: 0;
    }

    .resources-editor-container {
        margin-top: 1rem;
    }

    .resources-table {
        overflow-x: auto;
    }

    .resource-name {
        font-weight: 500;
        max-width: 250px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .resource-description {
        max-width: 300px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        color: #6b7280;
    }

    .resource-type-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 500;
    }

    .type-image {
        background: #dbeafe;
        color: #1e40af;
    }

    .type-pdf {
        background: #fee2e2;
        color: #991b1b;
    }

    .type-text {
        background: #d1fae5;
        color: #065f46;
    }

    .type-excel {
        background: #dcfce7;
        color: #166534;
    }

    .type-zip {
        background: #f3e8ff;
        color: #6b21a8;
    }

    .type-csv {
        background: #fef3c7;
        color: #92400e;
    }

    .type-table {
        background: #e0e7ff;
        color: #3730a3;
    }

    .type-timeseries {
        background: #cffafe;
        color: #0e7490;
    }
</style>
