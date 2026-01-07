<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { getAdminUsers, getAdminGroups, assignGroupToUser, removeGroupFromUser, createGroup, createUser, banUser, unbanUser, deleteUser, getUserInfo, getPromptModules, getTonalities, updatePromptModule, createTonality, createContentAgent, deleteTonality, setDefaultTonality, adminGetUserTonality, adminUpdateUserTonality, getGlobalResources, deleteResource, getTopics, createTopic, updateTopic, deleteTopic, recalculateAllTopicStats, reorderTopics, type PromptModule, type TonalityOption, type Resource, type Topic, type TopicCreate, type TopicUpdate } from '$lib/api';
    import { onMount, onDestroy } from 'svelte';
    import { goto } from '$app/navigation';
    import ResourceEditor from '$lib/components/ResourceEditor.svelte';
    import { navigationContext } from '$lib/stores/navigation';
    import { actionStore, type UIAction, type ActionResult } from '$lib/stores/actions';

    // Topics loaded from database
    let allTopics: Array<{ id: string; label: string }> = [];
    let dbTopics: Topic[] = [];
    let topicsLoading = true;

    let users: any[] = [];
    let groups: any[] = [];
    let loading = true;
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

    // New content agent form state
    let showNewContentAgentForm = false;
    let newContentAgentName = '';
    let newContentAgentTemplate = '';
    let newContentAgentDescription = '';
    let newContentAgentTopic = '';
    let newContentAgentSaving = false;

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

    // Topic management state
    let showCreateTopicModal = false;
    let newTopicSlug = '';
    let newTopicTitle = '';
    let newTopicDescription = '';
    let newTopicIcon = '';
    let newTopicColor = '#3b82f6';
    let createTopicLoading = false;
    let editingTopic: Topic | null = null;
    let editedTopicTitle = '';
    let editedTopicDescription = '';
    let editedTopicIcon = '';
    let editedTopicColor = '';
    let editedTopicVisible = true;
    let editedTopicActive = true;
    let editedTopicSearchable = true;
    let editedTopicAccessMainchat = true;
    let editedTopicArticleOrder = 'date';
    let editedTopicAgentType = '';
    let topicSaving = false;

    // Topic drag and drop state
    let draggedTopic: Topic | null = null;
    let dragOverIndex: number | null = null;

    // Prompt type labels
    const promptTypeLabels: Record<string, string> = {
        'general': 'General System Prompt',
        'chat_specific': 'Chat-Specific Prompt',
        'chat_constraint': 'Chat Constraint',
        'article_constraint': 'Article Constraint',
        'content_topic': 'Content Topic',
        'tonality': 'Tonality Style'
    };

    // View state: 'users', 'groups', 'prompts', 'resources', 'topics'
    let currentView: 'users' | 'groups' | 'prompts' | 'resources' | 'topics' = 'users';

    // Check permissions - require global:admin
    $: isGlobalAdmin = $auth.user?.scopes?.includes('global:admin') || false;

    // Redirect if no global admin access
    $: if ($auth.isAuthenticated && !isGlobalAdmin) {
        goto('/');
    }

    // Update navigation context when view changes
    $: if ($auth.isAuthenticated && isGlobalAdmin) {
        navigationContext.setContext({
            section: 'global_admin',
            topic: null,
            subNav: currentView,
            articleId: null,
            articleHeadline: null,
            role: 'admin'
        });
    }

    async function loadTopicsFromDb(recalculate: boolean = false) {
        try {
            topicsLoading = true;
            if (recalculate) {
                try {
                    await recalculateAllTopicStats();
                } catch (e) {
                    console.error('Failed to recalculate topic stats:', e);
                }
            }
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

            const [usersData, groupsData] = await Promise.all([
                getAdminUsers(),
                getAdminGroups()
            ]);
            users = usersData.sort((a: any, b: any) => a.email.localeCompare(b.email));
            groups = groupsData.sort((a: any, b: any) => a.name.localeCompare(b.name));
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to load admin data';
            console.error('Error loading admin data:', e);
        } finally {
            loading = false;
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

    $: if (currentView === 'resources') {
        loadGlobalResources();
    }

    function handleGlobalResourceRefresh() {
        loadGlobalResources();
    }

    function handleResourceError(event: CustomEvent<string>) {
        error = event.detail;
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

    async function handleDeleteResource(resourceId: number, resourceName: string) {
        if (!confirm(`Are you sure you want to delete the resource "${resourceName}"?`)) return;
        try {
            error = '';
            await deleteResource(resourceId);
            await loadGlobalResources();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to delete resource';
        }
    }

    // Prompt management functions
    async function loadPrompts() {
        try {
            promptsLoading = true;
            error = '';
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

    async function handleCreateContentAgent() {
        if (!newContentAgentName.trim() || !newContentAgentTemplate.trim() || !newContentAgentTopic) return;
        try {
            newContentAgentSaving = true;
            error = '';
            await createContentAgent(
                newContentAgentName.trim(),
                newContentAgentTemplate.trim(),
                newContentAgentTopic,
                newContentAgentDescription.trim() || undefined
            );
            await loadPrompts();
            showNewContentAgentForm = false;
            newContentAgentName = '';
            newContentAgentTemplate = '';
            newContentAgentDescription = '';
            newContentAgentTopic = '';
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to create content agent';
        } finally {
            newContentAgentSaving = false;
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
        for (const type of Object.keys(grouped)) {
            grouped[type].sort((a, b) => a.sort_order - b.sort_order);
        }
        return grouped;
    }

    $: groupedPrompts = getGroupedPrompts(prompts);

    $: if (currentView === 'prompts' && prompts.length === 0 && !promptsLoading) {
        loadPrompts();
    }

    $: if (currentView === 'prompts' && dbTopics.length === 0 && !topicsLoading) {
        loadTopicsFromDb();
    }

    // Load available tonalities for user management
    async function loadAvailableTonalities() {
        try {
            availableTonalities = await getTonalities();
        } catch (e) {
            console.error('Failed to load tonalities:', e);
        }
    }

    async function openUserTonalityModal(userId: number, userEmail: string) {
        userTonalityUserId = userId;
        userTonalityUserEmail = userEmail;
        showUserTonalityModal = true;
        userTonalityLoading = true;

        if (availableTonalities.length === 0) {
            await loadAvailableTonalities();
        }

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

    // Topic CRUD functions
    async function handleCreateTopic() {
        if (!newTopicSlug.trim() || !newTopicTitle.trim()) return;

        if (!/^[a-z][a-z0-9_]*$/.test(newTopicSlug)) {
            error = 'Slug must start with a letter and contain only lowercase letters, numbers, and underscores';
            return;
        }

        try {
            createTopicLoading = true;
            error = '';
            await createTopic({
                slug: newTopicSlug.trim(),
                title: newTopicTitle.trim(),
                description: newTopicDescription.trim() || undefined,
                icon: newTopicIcon.trim() || undefined,
                color: newTopicColor || undefined
            });
            await loadTopicsFromDb();
            await loadData();
            showCreateTopicModal = false;
            newTopicSlug = '';
            newTopicTitle = '';
            newTopicDescription = '';
            newTopicIcon = '';
            newTopicColor = '#3b82f6';
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to create topic';
        } finally {
            createTopicLoading = false;
        }
    }

    function startEditingTopic(topic: Topic) {
        editingTopic = topic;
        editedTopicTitle = topic.title;
        editedTopicDescription = topic.description || '';
        editedTopicIcon = topic.icon || '';
        editedTopicColor = topic.color || '#3b82f6';
        editedTopicVisible = topic.visible;
        editedTopicActive = topic.active;
        editedTopicSearchable = topic.searchable ?? true;
        editedTopicAccessMainchat = topic.access_mainchat ?? true;
        editedTopicArticleOrder = topic.article_order || 'date';
        editedTopicAgentType = topic.agent_type || '';
    }

    function cancelEditingTopic() {
        editingTopic = null;
    }

    async function saveTopicChanges() {
        if (!editingTopic) return;
        try {
            topicSaving = true;
            error = '';
            await updateTopic(editingTopic.slug, {
                title: editedTopicTitle,
                description: editedTopicDescription || undefined,
                icon: editedTopicIcon || undefined,
                color: editedTopicColor || undefined,
                visible: editedTopicVisible,
                active: editedTopicActive,
                searchable: editedTopicSearchable,
                access_mainchat: editedTopicAccessMainchat,
                article_order: editedTopicArticleOrder,
                agent_type: editedTopicAgentType || null
            });
            await loadTopicsFromDb();
            cancelEditingTopic();
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to save topic';
        } finally {
            topicSaving = false;
        }
    }

    async function handleDeleteTopic(topic: Topic) {
        if (topic.article_count > 0) {
            if (!confirm(`Topic "${topic.title}" has ${topic.article_count} articles. Articles will keep their content but lose their topic association. Are you sure you want to delete this topic?`)) return;
            if (!confirm('This action cannot be undone. The 4 groups for this topic will also be deleted. Continue?')) return;
            try {
                error = '';
                await deleteTopic(topic.slug, true);
                await loadTopicsFromDb();
                await loadData();
            } catch (e) {
                error = e instanceof Error ? e.message : 'Failed to delete topic';
            }
        } else {
            if (!confirm(`Are you sure you want to delete topic "${topic.title}"? The 4 groups for this topic will also be deleted.`)) return;
            try {
                error = '';
                await deleteTopic(topic.slug);
                await loadTopicsFromDb();
                await loadData();
            } catch (e) {
                error = e instanceof Error ? e.message : 'Failed to delete topic';
            }
        }
    }

    // Topic drag and drop handlers
    function handleTopicDragStart(e: DragEvent, topic: Topic) {
        draggedTopic = topic;
        if (e.dataTransfer) {
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', topic.slug);
        }
    }

    function handleTopicDragOver(e: DragEvent, index: number) {
        e.preventDefault();
        if (e.dataTransfer) {
            e.dataTransfer.dropEffect = 'move';
        }
        dragOverIndex = index;
    }

    function handleTopicDragLeave() {
        dragOverIndex = null;
    }

    async function handleTopicDrop(e: DragEvent, targetIndex: number) {
        e.preventDefault();
        dragOverIndex = null;

        if (!draggedTopic) return;

        const draggedIndex = dbTopics.findIndex(t => t.slug === draggedTopic!.slug);
        if (draggedIndex === targetIndex) {
            draggedTopic = null;
            return;
        }

        const newTopics = [...dbTopics];
        const [removed] = newTopics.splice(draggedIndex, 1);
        newTopics.splice(targetIndex, 0, removed);

        const reorderData = newTopics.map((t, idx) => ({
            slug: t.slug,
            sort_order: idx
        }));

        try {
            await reorderTopics(reorderData);
            dbTopics = newTopics.map((t, idx) => ({ ...t, sort_order: idx }));
            allTopics = dbTopics.map(t => ({ id: t.slug, label: t.title }));
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to reorder topics';
        }

        draggedTopic = null;
    }

    function handleTopicDragEnd() {
        draggedTopic = null;
        dragOverIndex = null;
    }

    // Update navigation context when a resource is selected
    function handleResourceSelect(resource: Resource) {
        navigationContext.setResource(resource.id, resource.name, resource.type);
    }

    // Action handlers for chat-triggered UI actions
    let actionUnsubscribers: (() => void)[] = [];

    async function handleSwitchGlobalViewAction(action: UIAction): Promise<ActionResult> {
        const view = action.params?.view;
        if (!view) {
            return { success: false, action: 'switch_global_view', error: 'No view specified' };
        }
        currentView = view as any;
        return { success: true, action: 'switch_global_view', message: `Switched to ${view} view` };
    }

    async function handleDeleteResourceAction(action: UIAction): Promise<ActionResult> {
        const resourceId = action.params?.resource_id;
        if (!resourceId) {
            return { success: false, action: 'delete_resource', error: 'No resource ID specified' };
        }
        if (!action.params?.confirmed) {
            return { success: false, action: 'delete_resource', error: 'Action requires confirmation' };
        }
        try {
            await deleteResource(resourceId);
            await loadGlobalResources();
            return { success: true, action: 'delete_resource', message: `Resource #${resourceId} deleted` };
        } catch (e) {
            return { success: false, action: 'delete_resource', error: e instanceof Error ? e.message : 'Failed to delete' };
        }
    }

    async function handleSelectResourceAction(action: UIAction): Promise<ActionResult> {
        const resourceId = action.params?.resource_id;
        if (!resourceId) {
            return { success: false, action: 'select_resource', error: 'No resource ID specified' };
        }
        const resource = resources.find(r => r.id === resourceId);
        if (resource) {
            handleResourceSelect(resource);
            return { success: true, action: 'select_resource', message: `Resource #${resourceId} selected` };
        }
        return { success: false, action: 'select_resource', error: `Resource #${resourceId} not found` };
    }

    // Handle select_topic by redirecting to topic admin
    async function handleSelectTopicAction(action: UIAction): Promise<ActionResult> {
        const topicSlug = action.params?.topic;
        if (!topicSlug) {
            return { success: false, action: 'select_topic', error: 'No topic specified' };
        }
        // Redirect to topic admin page - the topic will be selected there
        goto(`/admin?topic=${topicSlug}`);
        return { success: true, action: 'select_topic', message: `Navigating to topic admin: ${topicSlug}` };
    }

    onMount(() => {
        if (!$auth.isAuthenticated) {
            goto('/');
            return;
        }
        loadData();

        actionUnsubscribers.push(
            actionStore.registerHandler('switch_global_view', handleSwitchGlobalViewAction),
            actionStore.registerHandler('delete_resource', handleDeleteResourceAction),
            actionStore.registerHandler('select_resource', handleSelectResourceAction),
            actionStore.registerHandler('select_topic', handleSelectTopicAction)
        );
    });

    onDestroy(() => {
        actionUnsubscribers.forEach(unsub => unsub());
    });
</script>

<div class="admin-container">
    <div class="admin-header">
        <div class="header-left">
            <h1>Global Administration</h1>
        </div>
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
            <button
                class="action-btn"
                class:active={currentView === 'topics'}
                on:click={() => { currentView = 'topics'; loadTopicsFromDb(true); }}
            >
                Topics
            </button>
        </div>
    </div>

    {#if error}
        <div class="error-message">{error}</div>
    {/if}

    {#if loading}
        <div class="loading">Loading...</div>
    {:else}
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
                                        <button class="assign-btn" on:click={() => selectedUserId = user.id}>
                                            Assign Group
                                        </button>
                                        <button class="tonality-btn" on:click={() => openUserTonalityModal(user.id, user.email)}>
                                            Tonality
                                        </button>
                                        {#if user.active}
                                            <button class="ban-btn" on:click={() => handleBanUser(user.id, user.email)}>
                                                Ban
                                            </button>
                                        {:else}
                                            <button class="unban-btn" on:click={() => handleUnbanUser(user.id, user.email)}>
                                                Unban
                                            </button>
                                        {/if}
                                        <button class="delete-user-btn" on:click={() => handleDeleteUser(user.id, user.email)}>
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
                                <button class="add-users-btn" on:click={() => selectedGroupForUsers = group.name}>
                                    Add Users
                                </button>
                            </div>
                        </div>
                    {/each}
                </div>

                <div class="create-group">
                    <h3>Create New Group</h3>
                    <input type="text" bind:value={newGroupName} placeholder="Group name" />
                    <input type="text" bind:value={newGroupDescription} placeholder="Description (optional)" />
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
                    <div class="prompts-header-buttons">
                        <button class="add-tonality-btn" on:click={() => showNewTonalityForm = true}>
                            + New Tonality
                        </button>
                        <button class="add-tonality-btn" on:click={() => showNewContentAgentForm = true}>
                            + New Content Agent
                        </button>
                    </div>
                </div>
                <p class="section-hint">Manage system prompts for the AI chatbot and content generation.</p>

                {#if promptsLoading}
                    <div class="loading">Loading prompts...</div>
                {:else}
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
                                                    <button class="edit-prompt-btn" on:click={() => startEditingPrompt(prompt)}>
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
                                                <button class="edit-prompt-btn" on:click={() => startEditingPrompt(prompt)}>
                                                    Edit
                                                </button>
                                                {#if !prompt.is_default}
                                                    <button class="set-default-btn" on:click={() => handleSetDefaultTonality(prompt.id)}>
                                                        Set Default
                                                    </button>
                                                    <button class="delete-tonality-btn" on:click={() => handleDeleteTonality(prompt.id, prompt.name)}>
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
                        loading={resourcesLoading}
                        showDeleteButton={true}
                        showUnlinkButton={false}
                        on:refresh={handleGlobalResourceRefresh}
                        on:error={handleResourceError}
                    />
                </div>
            </section>
        {/if}

        <!-- Topics Admin View -->
        {#if currentView === 'topics'}
            <section class="section topics-admin-section">
                <div class="section-header">
                    <h2>Topic Management</h2>
                    <button class="create-topic-btn" on:click={() => showCreateTopicModal = true}>
                        + Create Topic
                    </button>
                </div>

                {#if topicsLoading}
                    <div class="loading">Loading topics...</div>
                {:else if dbTopics.length === 0}
                    <p class="no-topics">No topics found. Create your first topic to get started.</p>
                {:else}
                    <p class="topics-hint">Drag rows to reorder topics. The order affects navigation display.</p>
                    <table class="topics-table">
                        <thead>
                            <tr>
                                <th class="col-order">#</th>
                                <th class="col-title">Topic</th>
                                <th class="col-articles">Articles</th>
                                <th class="col-readers">Readers</th>
                                <th class="col-rating">Rating</th>
                                <th class="col-ai">AI</th>
                                <th class="col-status">Status</th>
                                <th class="col-actions">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each dbTopics as topic, index}
                                <tr
                                    class:inactive={!topic.active}
                                    class:dragging={draggedTopic?.slug === topic.slug}
                                    class:drag-over={dragOverIndex === index}
                                    draggable="true"
                                    on:dragstart={(e) => handleTopicDragStart(e, topic)}
                                    on:dragover={(e) => handleTopicDragOver(e, index)}
                                    on:dragleave={handleTopicDragLeave}
                                    on:drop={(e) => handleTopicDrop(e, index)}
                                    on:dragend={handleTopicDragEnd}
                                >
                                    <td class="col-order">
                                        <span class="drag-handle" title="Drag to reorder">&#x2630;</span>
                                        <span class="order-number">{index + 1}</span>
                                    </td>
                                    <td class="col-title">
                                        <div class="topic-title-cell">
                                            <strong>{topic.title}</strong>
                                            <code class="topic-slug">{topic.slug}</code>
                                            {#if topic.description}
                                                <span class="topic-desc">{topic.description}</span>
                                            {/if}
                                        </div>
                                    </td>
                                    <td class="col-articles">{topic.article_count}</td>
                                    <td class="col-readers">{topic.reader_count || 0}</td>
                                    <td class="col-rating">{topic.rating_average ? topic.rating_average.toFixed(1) : '-'}</td>
                                    <td class="col-ai">
                                        {#if topic.access_mainchat}
                                            <span class="ai-badge enabled" title="Main chat can query this topic">On</span>
                                        {:else}
                                            <span class="ai-badge disabled" title="Main chat cannot query this topic">Off</span>
                                        {/if}
                                    </td>
                                    <td class="col-status">
                                        <div class="status-badges">
                                            {#if topic.active && topic.visible}
                                                <span class="status-badge active">Active</span>
                                            {:else if !topic.active}
                                                <span class="status-badge inactive">Inactive</span>
                                            {:else if !topic.visible}
                                                <span class="status-badge hidden">Hidden</span>
                                            {/if}
                                        </div>
                                    </td>
                                    <td class="col-actions">
                                        <div class="action-buttons">
                                            <button class="btn-edit" on:click={() => startEditingTopic(topic)}>Edit</button>
                                            <button class="btn-delete" on:click={() => handleDeleteTopic(topic)}>Delete</button>
                                        </div>
                                    </td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                {/if}
            </section>
        {/if}
    {/if}
</div>

<!-- Modals will be included via a separate import in production, but for now inline -->
<!-- Create User Modal -->
{#if showCreateUserModal}
    <div class="modal-overlay" on:click={() => showCreateUserModal = false}>
        <div class="modal" on:click|stopPropagation>
            <h3>Create New User</h3>
            <p class="modal-hint">Create a user before they log in via OAuth. They can be assigned groups immediately.</p>

            <div class="form-group">
                <label for="new-user-email">Email *</label>
                <input id="new-user-email" type="email" bind:value={newUserEmail} placeholder="user@example.com" required />
            </div>

            <div class="form-group">
                <label for="new-user-name">First Name</label>
                <input id="new-user-name" type="text" bind:value={newUserName} placeholder="John" />
            </div>

            <div class="form-group">
                <label for="new-user-surname">Last Name</label>
                <input id="new-user-surname" type="text" bind:value={newUserSurname} placeholder="Doe" />
            </div>

            <p class="modal-note">The user will appear as "Pending" until they log in via LinkedIn OAuth.</p>

            <div class="modal-actions">
                <button class="primary" on:click={handleCreateUser} disabled={!newUserEmail.trim() || createUserLoading}>
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
                        <input type="checkbox" checked={selectedGroupNames.includes(group.name)} on:change={() => toggleGroupSelection(group.name)} />
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
                        <input type="checkbox" checked={selectedUserIds.includes(user.id)} on:change={() => toggleUserSelection(user.id)} />
                        <div class="user-info-modal">
                            <span class="group-name">{user.email}</span>
                            {#if user.name}
                                <span class="group-desc">{user.name}</span>
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
                    <input type="text" id="prompt-name" bind:value={editedName} placeholder="Prompt name" />
                </div>

                <div class="form-group">
                    <label for="prompt-description">Description</label>
                    <input type="text" id="prompt-description" bind:value={editedDescription} placeholder="Optional description" />
                </div>

                <div class="form-group">
                    <label for="prompt-template">Template Text</label>
                    <textarea id="prompt-template" bind:value={editedTemplateText} rows="12" placeholder="Enter the prompt template..."></textarea>
                </div>
            </div>

            <div class="modal-actions">
                <button on:click={savePromptChanges} disabled={promptSaving || !editedTemplateText.trim()}>
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
                    <input type="text" id="tonality-name" bind:value={newTonalityName} placeholder="e.g., Friendly, Formal, Technical" />
                </div>

                <div class="form-group">
                    <label for="tonality-description">Description</label>
                    <input type="text" id="tonality-description" bind:value={newTonalityDescription} placeholder="Brief description of this style" />
                </div>

                <div class="form-group">
                    <label for="tonality-template">Template Text *</label>
                    <textarea id="tonality-template" bind:value={newTonalityTemplate} rows="8" placeholder="Enter the tonality instructions..."></textarea>
                </div>
            </div>

            <div class="modal-actions">
                <button on:click={handleCreateTonality} disabled={newTonalitySaving || !newTonalityName.trim() || !newTonalityTemplate.trim()}>
                    {newTonalitySaving ? 'Creating...' : 'Create Tonality'}
                </button>
                <button on:click={() => showNewTonalityForm = false}>Cancel</button>
            </div>
        </div>
    </div>
{/if}

<!-- New Content Agent Modal -->
{#if showNewContentAgentForm}
    <div class="modal-overlay" on:click={() => showNewContentAgentForm = false}>
        <div class="modal prompt-modal" on:click|stopPropagation>
            <h3>Create New Content Agent</h3>
            <p class="modal-hint">Create a new content agent prompt for a specific topic.</p>

            <div class="prompt-edit-form">
                <div class="form-group">
                    <label for="agent-name">Name *</label>
                    <input type="text" id="agent-name" bind:value={newContentAgentName} placeholder="e.g., Technical Content Agent" />
                </div>

                <div class="form-group">
                    <label for="agent-topic">Topic *</label>
                    <select id="agent-topic" bind:value={newContentAgentTopic}>
                        <option value="">Select a topic...</option>
                        {#each dbTopics as topic}
                            <option value={topic.slug}>{topic.title}</option>
                        {/each}
                    </select>
                </div>

                <div class="form-group">
                    <label for="agent-description">Description</label>
                    <input type="text" id="agent-description" bind:value={newContentAgentDescription} placeholder="Brief description of this agent" />
                </div>

                <div class="form-group">
                    <label for="agent-template">Template Text *</label>
                    <textarea id="agent-template" bind:value={newContentAgentTemplate} rows="10" placeholder="Enter the content agent instructions..."></textarea>
                </div>
            </div>

            <div class="modal-actions">
                <button on:click={handleCreateContentAgent} disabled={newContentAgentSaving || !newContentAgentName.trim() || !newContentAgentTemplate.trim() || !newContentAgentTopic}>
                    {newContentAgentSaving ? 'Creating...' : 'Create Content Agent'}
                </button>
                <button on:click={() => showNewContentAgentForm = false}>Cancel</button>
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
                <button on:click={saveUserTonality} disabled={userTonalitySaving || userTonalityLoading}>
                    {userTonalitySaving ? 'Saving...' : 'Save Preferences'}
                </button>
                <button on:click={closeUserTonalityModal}>Cancel</button>
            </div>
        </div>
    </div>
{/if}

<!-- Create Topic Modal -->
{#if showCreateTopicModal}
    <div class="modal-overlay" on:click={() => showCreateTopicModal = false}>
        <div class="modal topic-modal" on:click|stopPropagation>
            <h3>Create New Topic</h3>
            <p class="modal-hint">Create a new research topic. 4 permission groups will be automatically created.</p>

            <div class="topic-form">
                <div class="form-group">
                    <label for="topic-slug">Slug *</label>
                    <input id="topic-slug" type="text" bind:value={newTopicSlug} placeholder="e.g., crypto, commodities" pattern="[a-z][a-z0-9_]*" />
                    <span class="help-text">Lowercase letters, numbers, underscores. Cannot be changed later.</span>
                </div>

                <div class="form-group">
                    <label for="topic-title">Title *</label>
                    <input id="topic-title" type="text" bind:value={newTopicTitle} placeholder="e.g., Cryptocurrency Research" />
                </div>

                <div class="form-group">
                    <label for="topic-description">Description</label>
                    <textarea id="topic-description" bind:value={newTopicDescription} placeholder="Brief description of this research topic..." rows="3"></textarea>
                </div>

                <div class="form-row">
                    <div class="form-group">
                        <label for="topic-icon">Icon</label>
                        <input id="topic-icon" type="text" bind:value={newTopicIcon} placeholder="e.g., chart, globe" />
                    </div>
                    <div class="form-group">
                        <label for="topic-color">Color</label>
                        <input id="topic-color" type="color" bind:value={newTopicColor} />
                    </div>
                </div>
            </div>

            <div class="modal-actions">
                <button on:click={handleCreateTopic} disabled={!newTopicSlug.trim() || !newTopicTitle.trim() || createTopicLoading}>
                    {createTopicLoading ? 'Creating...' : 'Create Topic'}
                </button>
                <button on:click={() => showCreateTopicModal = false}>Cancel</button>
            </div>
        </div>
    </div>
{/if}

<!-- Edit Topic Modal -->
{#if editingTopic !== null}
    <div class="modal-overlay" on:click={cancelEditingTopic}>
        <div class="modal topic-modal" on:click|stopPropagation>
            <h3>Edit Topic: {editingTopic.slug}</h3>
            <p class="modal-hint">Update topic settings. Slug cannot be changed.</p>

            <div class="topic-form">
                <div class="form-group">
                    <label for="edit-topic-title">Title *</label>
                    <input id="edit-topic-title" type="text" bind:value={editedTopicTitle} placeholder="Topic title" />
                </div>

                <div class="form-group">
                    <label for="edit-topic-description">Description</label>
                    <textarea id="edit-topic-description" bind:value={editedTopicDescription} placeholder="Brief description..." rows="3"></textarea>
                </div>

                <div class="form-group">
                    <label for="edit-topic-icon">Icon</label>
                    <input id="edit-topic-icon" type="text" bind:value={editedTopicIcon} placeholder="Icon name" />
                </div>

                <div class="form-group checkboxes">
                    <label class="checkbox-label">
                        <input type="checkbox" bind:checked={editedTopicActive} />
                        <span>Active</span>
                        <span class="help-text">When inactive, topic is hidden from navigation</span>
                    </label>
                    <label class="checkbox-label">
                        <input type="checkbox" bind:checked={editedTopicVisible} />
                        <span>Visible</span>
                        <span class="help-text">When hidden, topic doesn't appear in public lists</span>
                    </label>
                    <label class="checkbox-label">
                        <input type="checkbox" bind:checked={editedTopicSearchable} />
                        <span>Searchable</span>
                        <span class="help-text">Allow content to appear in search results</span>
                    </label>
                    <label class="checkbox-label">
                        <input type="checkbox" bind:checked={editedTopicAccessMainchat} />
                        <span>AI Access</span>
                        <span class="help-text">Main chat can query this topic's content agent</span>
                    </label>
                </div>
            </div>

            <div class="form-group">
                <label for="edit-article-order">Article Ordering</label>
                <select id="edit-article-order" bind:value={editedTopicArticleOrder}>
                    <option value="date">By Date (newest first)</option>
                    <option value="priority">By Priority (highest first)</option>
                    <option value="title">By Title (alphabetical)</option>
                </select>
                <span class="help-text">How articles are sorted in listings. Sticky articles always appear first.</span>
            </div>

            <div class="form-group">
                <label for="edit-agent-type">Content Agent Type</label>
                <select id="edit-agent-type" bind:value={editedTopicAgentType}>
                    <option value="">None (no content agent)</option>
                    <option value="macro">Macro (macroeconomic analysis)</option>
                    <option value="equity">Equity (stock market analysis)</option>
                    <option value="fixed_income">Fixed Income (bond market analysis)</option>
                    <option value="esg">ESG (sustainability analysis)</option>
                    <option value="technical">Technical (technical documentation)</option>
                </select>
                <span class="help-text">The AI agent used for generating content in this topic.</span>
            </div>

            <div class="modal-actions">
                <button on:click={saveTopicChanges} disabled={!editedTopicTitle.trim() || topicSaving}>
                    {topicSaving ? 'Saving...' : 'Save Changes'}
                </button>
                <button on:click={cancelEditingTopic}>Cancel</button>
            </div>
        </div>
    </div>
{/if}

<style>
    :global(body) {
        background: #fafafa;
    }

    .admin-container {
        max-width: 1600px;
        margin: 0 auto;
        background: white;
        min-height: 100vh;
    }

    .admin-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1rem 1.5rem;
        background: white;
        border-bottom: 1px solid #e5e7eb;
        margin-bottom: 2rem;
    }

    .header-left h1 {
        margin: 0;
        font-size: 1.25rem;
        font-weight: 600;
        color: #1f2937;
    }

    .admin-actions {
        display: flex;
        gap: 0.5rem;
    }

    .action-btn {
        padding: 0.5rem 1rem;
        background: #f3f4f6;
        color: #374151;
        border: 1px solid #e5e7eb;
        border-radius: 6px;
        font-size: 0.875rem;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.15s ease;
    }

    .action-btn:hover {
        background: #e5e7eb;
        border-color: #d1d5db;
    }

    .action-btn.active {
        background: #6366f1;
        color: white;
        border-color: #6366f1;
    }

    .section {
        padding: 0 2rem 2rem;
    }

    .section-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1rem;
    }

    .section h2 {
        margin: 0 0 1rem 0;
        font-size: 1.25rem;
        color: #1f2937;
    }

    .section-hint {
        color: #6b7280;
        font-size: 0.875rem;
        margin-bottom: 1rem;
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
        margin: 0 2rem 1rem;
        border-radius: 6px;
        border: 1px solid #fecaca;
    }

    /* Tables */
    table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.875rem;
    }

    th, td {
        text-align: left;
        padding: 0.75rem 1rem;
        border-bottom: 1px solid #e5e7eb;
    }

    th {
        background: #f9fafb;
        font-weight: 600;
        color: #374151;
    }

    tr:hover {
        background: #f9fafb;
    }

    tr.banned {
        background: #fef2f2;
    }

    tr.inactive {
        opacity: 0.6;
    }

    /* Status badges */
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
        background: #dcfce7;
        color: #166534;
    }

    .status-badge.pending {
        background: #fef3c7;
        color: #92400e;
    }

    .status-badge.banned {
        background: #fecaca;
        color: #991b1b;
    }

    .status-badge.inactive {
        background: #f3f4f6;
        color: #6b7280;
    }

    .status-badge.hidden {
        background: #fef3c7;
        color: #92400e;
    }

    /* Groups badges */
    .groups-badges {
        display: flex;
        flex-wrap: wrap;
        gap: 0.25rem;
    }

    .group-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.25rem;
        padding: 0.25rem 0.5rem;
        background: #eff6ff;
        color: #1d4ed8;
        border-radius: 4px;
        font-size: 0.75rem;
    }

    .remove-group {
        background: none;
        border: none;
        color: #1d4ed8;
        cursor: pointer;
        font-size: 0.75rem;
        padding: 0;
        margin-left: 0.25rem;
    }

    .remove-group:hover {
        color: #dc2626;
    }

    /* Buttons */
    .user-actions {
        display: flex;
        gap: 0.5rem;
    }

    .assign-btn, .tonality-btn, .ban-btn, .unban-btn, .delete-user-btn, .create-user-btn, .add-users-btn {
        padding: 0.375rem 0.75rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 500;
        cursor: pointer;
        border: none;
    }

    .assign-btn {
        background: #3b82f6;
        color: white;
    }

    .tonality-btn {
        background: #8b5cf6;
        color: white;
    }

    .ban-btn {
        background: #f59e0b;
        color: white;
    }

    .unban-btn {
        background: #10b981;
        color: white;
    }

    .delete-user-btn {
        background: #ef4444;
        color: white;
    }

    .create-user-btn, .create-topic-btn {
        background: #3b82f6;
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 6px;
        font-size: 0.875rem;
    }

    .add-users-btn {
        background: #3b82f6;
        color: white;
    }

    /* Groups List */
    .groups-list {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
        gap: 1rem;
        margin-bottom: 2rem;
    }

    .group-card {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 1rem;
    }

    .group-card-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
    }

    .group-card h3 {
        margin: 0 0 0.25rem;
        font-size: 1rem;
    }

    .group-card p {
        margin: 0 0 0.5rem;
        color: #6b7280;
        font-size: 0.875rem;
    }

    .user-count {
        font-size: 0.75rem;
        color: #9ca3af;
    }

    .create-group {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 1.5rem;
        background: #f9fafb;
    }

    .create-group h3 {
        margin: 0 0 1rem;
    }

    .create-group input {
        display: block;
        width: 100%;
        padding: 0.75rem;
        margin-bottom: 0.75rem;
        border: 1px solid #e5e7eb;
        border-radius: 6px;
        font-size: 0.875rem;
    }

    .create-group button {
        background: #3b82f6;
        color: white;
        padding: 0.75rem 1.5rem;
        border: none;
        border-radius: 6px;
        font-weight: 500;
        cursor: pointer;
    }

    .create-group button:disabled {
        background: #9ca3af;
        cursor: not-allowed;
    }

    /* Prompts */
    .prompts-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.5rem;
    }

    .prompts-header-buttons {
        display: flex;
        gap: 0.5rem;
    }

    .add-tonality-btn {
        background: #8b5cf6;
        color: white;
        padding: 0.5rem 1rem;
        border: none;
        border-radius: 6px;
        font-size: 0.875rem;
        font-weight: 500;
        cursor: pointer;
    }

    .prompts-group {
        margin-bottom: 2rem;
    }

    .prompts-group h3 {
        margin: 0 0 1rem;
        font-size: 1rem;
        color: #374151;
    }

    .prompt-type-section {
        margin-bottom: 1.5rem;
    }

    .prompt-type-section h4 {
        margin: 0 0 0.75rem;
        font-size: 0.875rem;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .prompt-card, .tonality-card {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 0.75rem;
    }

    .prompt-card-header, .tonality-card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.5rem;
    }

    .prompt-info, .tonality-info {
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .prompt-name, .tonality-name {
        font-weight: 600;
    }

    .prompt-group-badge {
        background: #eff6ff;
        color: #1d4ed8;
        padding: 0.125rem 0.5rem;
        border-radius: 4px;
        font-size: 0.75rem;
    }

    .default-badge {
        background: #dcfce7;
        color: #166534;
        padding: 0.125rem 0.5rem;
        border-radius: 4px;
        font-size: 0.75rem;
    }

    .prompt-actions, .tonality-actions {
        display: flex;
        gap: 0.5rem;
    }

    .edit-prompt-btn, .set-default-btn, .delete-tonality-btn {
        padding: 0.375rem 0.75rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 500;
        cursor: pointer;
        border: none;
    }

    .edit-prompt-btn {
        background: #3b82f6;
        color: white;
    }

    .set-default-btn {
        background: #10b981;
        color: white;
    }

    .delete-tonality-btn {
        background: #ef4444;
        color: white;
    }

    .prompt-description, .tonality-description {
        color: #6b7280;
        font-size: 0.875rem;
        margin: 0 0 0.5rem;
    }

    .prompt-preview, .tonality-preview {
        background: #f9fafb;
        padding: 0.75rem;
        border-radius: 4px;
        font-size: 0.8rem;
        color: #6b7280;
        font-family: monospace;
        margin-bottom: 0.5rem;
    }

    .prompt-meta {
        display: flex;
        gap: 1rem;
        font-size: 0.75rem;
        color: #9ca3af;
    }

    .tonality-hint {
        color: #6b7280;
        font-size: 0.875rem;
        margin-bottom: 1rem;
    }

    .tonality-list {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
        gap: 1rem;
    }

    .tonality-card.is-default {
        border-color: #10b981;
        background: #f0fdf4;
    }

    /* Resources */
    .resources-editor-container {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 1rem;
    }

    /* Topics Table */
    .topics-table {
        width: 100%;
    }

    .topics-hint {
        color: #6b7280;
        font-size: 0.875rem;
        margin-bottom: 1rem;
    }

    .no-topics {
        color: #6b7280;
        text-align: center;
        padding: 2rem;
    }

    .col-order {
        width: 60px;
    }

    .col-articles, .col-readers, .col-rating, .col-ai {
        width: 80px;
        text-align: center;
    }

    .col-status {
        width: 100px;
    }

    .col-actions {
        width: 120px;
    }

    .drag-handle {
        cursor: grab;
        color: #9ca3af;
        margin-right: 0.5rem;
    }

    .order-number {
        color: #6b7280;
    }

    .topic-title-cell {
        display: flex;
        flex-direction: column;
        gap: 0.125rem;
    }

    .topic-slug {
        font-size: 0.75rem;
        color: #9ca3af;
        background: #f3f4f6;
        padding: 0.125rem 0.375rem;
        border-radius: 3px;
    }

    .topic-desc {
        font-size: 0.8rem;
        color: #6b7280;
    }

    .ai-badge {
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 500;
    }

    .ai-badge.enabled {
        background: #dcfce7;
        color: #166534;
    }

    .ai-badge.disabled {
        background: #f3f4f6;
        color: #6b7280;
    }

    .action-buttons {
        display: flex;
        gap: 0.5rem;
    }

    .btn-edit, .btn-delete {
        padding: 0.375rem 0.75rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 500;
        cursor: pointer;
        border: none;
    }

    .btn-edit {
        background: #3b82f6;
        color: white;
    }

    .btn-delete {
        background: #ef4444;
        color: white;
    }

    tr.dragging {
        opacity: 0.5;
    }

    tr.drag-over {
        background: #eff6ff;
        border-top: 2px solid #3b82f6;
    }

    /* Modals */
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
        max-width: 600px;
        max-height: 90vh;
        overflow-y: auto;
    }

    .modal.prompt-modal, .modal.topic-modal {
        min-width: 600px;
        max-width: 800px;
    }

    .modal h3 {
        margin: 0 0 0.5rem;
    }

    .modal-hint {
        color: #6b7280;
        font-size: 0.875rem;
        margin-bottom: 1rem;
    }

    .modal-note {
        color: #6b7280;
        font-size: 0.875rem;
        background: #f9fafb;
        padding: 0.75rem;
        border-radius: 4px;
        margin: 1rem 0;
    }

    .form-group {
        margin-bottom: 1rem;
    }

    .form-group label {
        display: block;
        margin-bottom: 0.375rem;
        font-weight: 500;
        color: #374151;
        font-size: 0.875rem;
    }

    .form-group input, .form-group textarea, .form-group select {
        width: 100%;
        padding: 0.75rem;
        border: 1px solid #e5e7eb;
        border-radius: 6px;
        font-size: 0.875rem;
    }

    .form-group textarea {
        font-family: monospace;
        resize: vertical;
    }

    .help-text {
        display: block;
        font-size: 0.75rem;
        color: #9ca3af;
        margin-top: 0.25rem;
    }

    .form-row {
        display: flex;
        gap: 1rem;
    }

    .form-row .form-group {
        flex: 1;
    }

    .form-group.checkboxes {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
    }

    .checkbox-label {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        cursor: pointer;
    }

    .checkbox-label input {
        width: auto;
    }

    .checkbox-label span {
        font-weight: 500;
    }

    .checkbox-label .help-text {
        margin: 0;
        margin-left: auto;
    }

    .groups-checklist {
        max-height: 300px;
        overflow-y: auto;
        border: 1px solid #e5e7eb;
        border-radius: 6px;
        padding: 0.5rem;
        margin-bottom: 1rem;
    }

    .group-checkbox {
        display: flex;
        align-items: flex-start;
        gap: 0.5rem;
        padding: 0.5rem;
        cursor: pointer;
    }

    .group-checkbox:hover {
        background: #f9fafb;
    }

    .group-checkbox input {
        margin-top: 0.25rem;
    }

    .group-name {
        font-weight: 500;
    }

    .group-desc {
        font-size: 0.8rem;
        color: #6b7280;
    }

    .user-info-modal {
        display: flex;
        flex-direction: column;
    }

    .modal-actions {
        display: flex;
        justify-content: flex-end;
        gap: 0.75rem;
        margin-top: 1.5rem;
    }

    .modal-actions button {
        padding: 0.75rem 1.5rem;
        border-radius: 6px;
        font-weight: 500;
        cursor: pointer;
        border: none;
    }

    .modal-actions button:first-child, .modal-actions button.primary {
        background: #3b82f6;
        color: white;
    }

    .modal-actions button:first-child:disabled, .modal-actions button.primary:disabled {
        background: #9ca3af;
        cursor: not-allowed;
    }

    .modal-actions button:last-child:not(.primary) {
        background: #f3f4f6;
        color: #374151;
    }

    .tonality-form {
        margin-bottom: 1rem;
    }
</style>
