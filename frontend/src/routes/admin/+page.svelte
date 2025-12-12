<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { getAdminUsers, getAdminGroups, assignGroupToUser, removeGroupFromUser, createGroup } from '$lib/api';
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';

    let users: any[] = [];
    let groups: any[] = [];
    let loading = true;
    let error = '';
    let selectedUserId: number | null = null;
    let selectedGroupName = '';
    let newGroupName = '';
    let newGroupDescription = '';

    // Check if user is admin
    $: if (!$auth.isAuthenticated || !$auth.user?.scopes?.includes('admin')) {
        goto('/');
    }

    async function loadData() {
        try {
            loading = true;
            error = '';
            const [usersData, groupsData] = await Promise.all([
                getAdminUsers(),
                getAdminGroups()
            ]);
            users = usersData;
            groups = groupsData;
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to load admin data';
            console.error('Error loading admin data:', e);
        } finally {
            loading = false;
        }
    }

    async function handleAssignGroup() {
        if (!selectedUserId || !selectedGroupName) return;

        try {
            error = '';
            await assignGroupToUser(selectedUserId, selectedGroupName);
            await loadData();
            selectedUserId = null;
            selectedGroupName = '';
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to assign group';
        }
    }

    async function handleRemoveGroup(userId: number, groupName: string) {
        if (!confirm(`Remove group "${groupName}" from this user?`)) return;

        try {
            error = '';
            await removeGroupFromUser(userId, groupName);
            await loadData();
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

    onMount(() => {
        loadData();
    });
</script>

<div class="admin-container">
    <header>
        <h1>Admin Panel</h1>
        <a href="/" class="back-link">Back to Chat</a>
    </header>

    {#if error}
        <div class="error-message">{error}</div>
    {/if}

    {#if loading}
        <div class="loading">Loading...</div>
    {:else}
        <div class="admin-sections">
            <!-- Groups Section -->
            <section class="section">
                <h2>Groups</h2>
                <div class="groups-list">
                    {#each groups as group}
                        <div class="group-card">
                            <h3>{group.name}</h3>
                            {#if group.description}
                                <p>{group.description}</p>
                            {/if}
                            <span class="user-count">{group.user_count} users</span>
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

            <!-- Users Section -->
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
                                    <td>{user.name} {user.surname || ''}</td>
                                    <td>
                                        <div class="user-groups">
                                            {#each user.groups as groupName}
                                                <span class="group-badge">
                                                    {groupName}
                                                    <button
                                                        class="remove-btn"
                                                        on:click={() => handleRemoveGroup(user.id, groupName)}
                                                        title="Remove group"
                                                    >
                                                        ×
                                                    </button>
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
        </div>
    {/if}
</div>

<!-- Assign Group Modal -->
{#if selectedUserId !== null}
    <div class="modal-overlay" on:click={() => selectedUserId = null}>
        <div class="modal" on:click|stopPropagation>
            <h3>Assign Group to User</h3>
            <select bind:value={selectedGroupName}>
                <option value="">Select a group...</option>
                {#each groups as group}
                    <option value={group.name}>{group.name}</option>
                {/each}
            </select>
            <div class="modal-actions">
                <button on:click={handleAssignGroup} disabled={!selectedGroupName}>
                    Assign
                </button>
                <button on:click={() => selectedUserId = null}>Cancel</button>
            </div>
        </div>
    </div>
{/if}

<style>
    .admin-container {
        max-width: 1400px;
        margin: 0 auto;
        padding: 2rem;
    }

    header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 2rem;
    }

    header h1 {
        margin: 0;
        color: #333;
    }

    .back-link {
        color: #0077b5;
        text-decoration: none;
        font-weight: 500;
    }

    .back-link:hover {
        text-decoration: underline;
    }

    .error-message {
        background: #ffebee;
        color: #d32f2f;
        padding: 1rem;
        border-radius: 4px;
        margin-bottom: 1rem;
    }

    .loading {
        text-align: center;
        padding: 2rem;
        color: #666;
    }

    .admin-sections {
        display: grid;
        grid-template-columns: 1fr 2fr;
        gap: 2rem;
    }

    .section {
        background: white;
        padding: 1.5rem;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }

    .section h2 {
        margin-top: 0;
        color: #333;
        border-bottom: 2px solid #0077b5;
        padding-bottom: 0.5rem;
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

    .group-card h3 {
        margin: 0 0 0.5rem 0;
        color: #0077b5;
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
        background: #0077b5;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-weight: 500;
    }

    .create-group button:hover:not(:disabled) {
        background: #006399;
    }

    .create-group button:disabled {
        background: #ccc;
        cursor: not-allowed;
    }

    .users-table {
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

    .user-groups {
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

    .remove-btn {
        background: none;
        border: none;
        color: #d32f2f;
        font-size: 1.2rem;
        line-height: 1;
        cursor: pointer;
        padding: 0;
        margin-left: 0.25rem;
    }

    .remove-btn:hover {
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
    }

    .modal select {
        width: 100%;
        padding: 0.75rem;
        margin-bottom: 1rem;
        border: 1px solid #ddd;
        border-radius: 4px;
        font-family: inherit;
        font-size: 1rem;
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
</style>
