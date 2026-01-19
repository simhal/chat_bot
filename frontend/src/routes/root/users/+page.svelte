<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import {
		assignGroupToUser,
		removeGroupFromUser,
		createUser,
		banUser,
		unbanUser,
		deleteUser,
		getUserInfo,
		adminGetUserTonality,
		adminUpdateUserTonality,
		type TonalityOption
	} from '$lib/api';
	import { actionStore, type UIAction, type ActionResult } from '$lib/stores/actions';
	import { onMount, onDestroy } from 'svelte';

	// Get shared state from layout context
	const users = getContext<Writable<any[]>>('rootAdminUsers');
	const groups = getContext<Writable<any[]>>('rootAdminGroups');
	const availableTonalities = getContext<Writable<TonalityOption[]>>('rootAdminTonalities');
	const loadData = getContext<() => Promise<void>>('rootAdminLoadData');
	const loadTonalities = getContext<() => Promise<void>>('rootAdminLoadTonalities');

	let selectedUserId: number | null = null;
	let selectedGroupNames: string[] = [];
	let error = '';

	// Create user modal state
	let showCreateUserModal = false;
	let newUserEmail = '';
	let newUserName = '';
	let newUserSurname = '';
	let createUserLoading = false;

	// User tonality management
	let showUserTonalityModal = false;
	let userTonalityUserId: number | null = null;
	let userTonalityUserEmail = '';
	let userTonalityLoading = false;
	let userTonalitySaving = false;
	let selectedUserChatTonality: number | null = null;
	let selectedUserContentTonality: number | null = null;

	async function handleAssignGroup() {
		if (!selectedUserId || selectedGroupNames.length === 0) return;
		try {
			error = '';
			for (const groupName of selectedGroupNames) {
				await assignGroupToUser(selectedUserId, groupName);
			}
			await loadData();
			selectedGroupNames = [];
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to assign group';
		}
	}

	async function handleRemoveGroup(userId: number, groupName: string) {
		try {
			error = '';
			await removeGroupFromUser(userId, groupName);
			await loadData();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to remove group';
		}
	}

	async function handleCreateUser() {
		if (!newUserEmail) return;
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

	async function handleBanUser(userId: number) {
		if (!confirm('Are you sure you want to ban this user?')) return;
		try {
			error = '';
			await banUser(userId);
			await loadData();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to ban user';
		}
	}

	async function handleUnbanUser(userId: number) {
		try {
			error = '';
			await unbanUser(userId);
			await loadData();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to unban user';
		}
	}

	async function handleDeleteUser(userId: number) {
		if (!confirm('Are you sure you want to permanently delete this user? This cannot be undone.'))
			return;
		try {
			error = '';
			await deleteUser(userId);
			await loadData();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to delete user';
		}
	}

	async function openUserTonalityModal(userId: number, userEmail: string) {
		userTonalityUserId = userId;
		userTonalityUserEmail = userEmail;
		showUserTonalityModal = true;
		userTonalityLoading = true;

		try {
			await loadTonalities();
			const userTonality = await adminGetUserTonality(userId);
			selectedUserChatTonality = userTonality.chat_tonality?.id || null;
			selectedUserContentTonality = userTonality.content_tonality?.id || null;
		} catch (e) {
			console.error('Failed to load user tonality:', e);
		} finally {
			userTonalityLoading = false;
		}
	}

	async function saveUserTonality() {
		if (!userTonalityUserId) return;
		try {
			userTonalitySaving = true;
			await adminUpdateUserTonality(
				userTonalityUserId,
				selectedUserChatTonality,
				selectedUserContentTonality
			);
			showUserTonalityModal = false;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to update user tonality';
		} finally {
			userTonalitySaving = false;
		}
	}

	// Action handlers
	let actionUnsubscribers: (() => void)[] = [];

	async function handleCreateUserAction(action: UIAction): Promise<ActionResult> {
		const email = action.params?.email;
		if (!email) {
			return { success: false, action: 'create_user', error: 'No email specified' };
		}
		try {
			await createUser(email, action.params?.name, action.params?.surname);
			await loadData();
			return { success: true, action: 'create_user', message: `User ${email} created` };
		} catch (e) {
			return {
				success: false,
				action: 'create_user',
				error: e instanceof Error ? e.message : 'Failed to create user'
			};
		}
	}

	async function handleBanUserAction(action: UIAction): Promise<ActionResult> {
		const userId = action.params?.user_id;
		if (!userId) {
			return { success: false, action: 'ban_user', error: 'No user_id specified' };
		}
		if (!action.params?.confirmed) {
			return { success: false, action: 'ban_user', error: 'Action requires confirmation' };
		}
		try {
			await banUser(userId);
			await loadData();
			return { success: true, action: 'ban_user', message: 'User banned' };
		} catch (e) {
			return {
				success: false,
				action: 'ban_user',
				error: e instanceof Error ? e.message : 'Failed'
			};
		}
	}

	async function handleUnbanUserAction(action: UIAction): Promise<ActionResult> {
		const userId = action.params?.user_id;
		if (!userId) {
			return { success: false, action: 'unban_user', error: 'No user_id specified' };
		}
		try {
			await unbanUser(userId);
			await loadData();
			return { success: true, action: 'unban_user', message: 'User unbanned' };
		} catch (e) {
			return {
				success: false,
				action: 'unban_user',
				error: e instanceof Error ? e.message : 'Failed'
			};
		}
	}

	async function handleDeleteUserAction(action: UIAction): Promise<ActionResult> {
		const userId = action.params?.user_id;
		if (!userId) {
			return { success: false, action: 'delete_user', error: 'No user_id specified' };
		}
		if (!action.params?.confirmed) {
			return { success: false, action: 'delete_user', error: 'Action requires confirmation' };
		}
		try {
			await deleteUser(userId);
			await loadData();
			return { success: true, action: 'delete_user', message: 'User deleted' };
		} catch (e) {
			return {
				success: false,
				action: 'delete_user',
				error: e instanceof Error ? e.message : 'Failed'
			};
		}
	}

	onMount(() => {
		actionUnsubscribers.push(
			actionStore.registerHandler('create_user', handleCreateUserAction),
			actionStore.registerHandler('ban_user', handleBanUserAction),
			actionStore.registerHandler('unban_user', handleUnbanUserAction),
			actionStore.registerHandler('delete_user', handleDeleteUserAction)
		);
	});

	onDestroy(() => {
		actionUnsubscribers.forEach((unsub) => unsub());
	});
</script>

<div class="users-view">
	{#if error}
		<div class="error-message">{error}</div>
	{/if}

	<div class="view-header">
		<h2>User Management</h2>
		<button class="btn-primary" on:click={() => (showCreateUserModal = true)}>Create User</button>
	</div>

	<div class="users-table" data-testid="user-list">
		<table>
			<thead>
				<tr>
					<th>Email</th>
					<th>Name</th>
					<th>Groups</th>
					<th>Status</th>
					<th>Actions</th>
				</tr>
			</thead>
			<tbody>
				{#each $users as user}
					<tr class:banned={user.is_banned} data-testid="user-row">
						<td>{user.email}</td>
						<td>{user.name || ''} {user.surname || ''}</td>
						<td>
							<div class="group-badges">
								{#each user.groups || [] as group}
									<span class="group-badge">
										{group}
										<button
											class="remove-btn"
											on:click={() => handleRemoveGroup(user.id, group)}
											title="Remove group"
										>
											x
										</button>
									</span>
								{/each}
							</div>
						</td>
						<td>
							{#if user.is_banned}
								<span class="status-badge banned">Banned</span>
							{:else}
								<span class="status-badge active">Active</span>
							{/if}
						</td>
						<td>
							<div class="action-buttons">
								<button
									class="btn-sm"
									on:click={() => {
										selectedUserId = user.id;
									}}
								>
									Assign Group
								</button>
								<button
									class="btn-sm"
									on:click={() => openUserTonalityModal(user.id, user.email)}
								>
									Tonality
								</button>
								{#if user.is_banned}
									<button class="btn-sm btn-success" on:click={() => handleUnbanUser(user.id)}>
										Unban
									</button>
								{:else}
									<button class="btn-sm btn-warning" on:click={() => handleBanUser(user.id)}>
										Ban
									</button>
								{/if}
								<button class="btn-sm btn-danger" on:click={() => handleDeleteUser(user.id)}>
									Delete
								</button>
							</div>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<!-- Assign Group Section -->
	{#if selectedUserId}
		<div class="assign-group-section">
			<h3>Assign Groups to User #{selectedUserId}</h3>
			<div class="form-row">
				<select multiple bind:value={selectedGroupNames}>
					{#each $groups as group}
						<option value={group.name}>{group.name}</option>
					{/each}
				</select>
				<button on:click={handleAssignGroup}>Assign</button>
				<button class="btn-secondary" on:click={() => (selectedUserId = null)}>Cancel</button>
			</div>
		</div>
	{/if}
</div>

<!-- Create User Modal -->
{#if showCreateUserModal}
	<div class="modal-overlay" on:click={() => (showCreateUserModal = false)}>
		<div class="modal" on:click|stopPropagation>
			<h3>Create New User</h3>
			<div class="form-group">
				<label for="new-user-email">Email (required)</label>
				<input id="new-user-email" type="email" bind:value={newUserEmail} />
			</div>
			<div class="form-group">
				<label for="new-user-name">First Name</label>
				<input id="new-user-name" type="text" bind:value={newUserName} />
			</div>
			<div class="form-group">
				<label for="new-user-surname">Last Name</label>
				<input id="new-user-surname" type="text" bind:value={newUserSurname} />
			</div>
			<div class="modal-actions">
				<button on:click={handleCreateUser} disabled={createUserLoading || !newUserEmail}>
					{createUserLoading ? 'Creating...' : 'Create'}
				</button>
				<button class="btn-secondary" on:click={() => (showCreateUserModal = false)}>
					Cancel
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- User Tonality Modal -->
{#if showUserTonalityModal}
	<div class="modal-overlay" on:click={() => (showUserTonalityModal = false)}>
		<div class="modal" on:click|stopPropagation>
			<h3>Tonality Settings for {userTonalityUserEmail}</h3>
			{#if userTonalityLoading}
				<p>Loading...</p>
			{:else}
				<div class="form-group">
					<label for="user-chat-tonality">Chat Tonality</label>
					<select id="user-chat-tonality" bind:value={selectedUserChatTonality}>
						<option value={null}>Default</option>
						{#each $availableTonalities as tonality}
							<option value={tonality.id}>{tonality.name}</option>
						{/each}
					</select>
				</div>
				<div class="form-group">
					<label for="user-content-tonality">Content Tonality</label>
					<select id="user-content-tonality" bind:value={selectedUserContentTonality}>
						<option value={null}>Default</option>
						{#each $availableTonalities as tonality}
							<option value={tonality.id}>{tonality.name}</option>
						{/each}
					</select>
				</div>
				<div class="modal-actions">
					<button on:click={saveUserTonality} disabled={userTonalitySaving}>
						{userTonalitySaving ? 'Saving...' : 'Save'}
					</button>
					<button class="btn-secondary" on:click={() => (showUserTonalityModal = false)}>
						Cancel
					</button>
				</div>
			{/if}
		</div>
	</div>
{/if}

<style>
	.users-view {
		padding: 0 2rem 2rem;
	}

	.view-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1.5rem;
	}

	.view-header h2 {
		margin: 0;
		font-size: 1.25rem;
		color: #1f2937;
	}

	.error-message {
		background: #fef2f2;
		color: #dc2626;
		padding: 1rem;
		margin-bottom: 1rem;
		border-radius: 6px;
		border: 1px solid #fecaca;
	}

	.users-table {
		background: white;
		border: 1px solid #e5e7eb;
		border-radius: 8px;
		overflow: hidden;
	}

	table {
		width: 100%;
		border-collapse: collapse;
	}

	th,
	td {
		padding: 0.75rem 1rem;
		text-align: left;
		border-bottom: 1px solid #e5e7eb;
	}

	th {
		background: #f9fafb;
		font-weight: 600;
		color: #374151;
		font-size: 0.875rem;
	}

	tr.banned {
		background: #fef2f2;
	}

	.group-badges {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem;
	}

	.group-badge {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0.125rem 0.5rem;
		background: #e0f2fe;
		color: #0369a1;
		border-radius: 4px;
		font-size: 0.75rem;
	}

	.remove-btn {
		background: none;
		border: none;
		color: #dc2626;
		cursor: pointer;
		padding: 0;
		font-size: 0.875rem;
		line-height: 1;
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

	.status-badge.banned {
		background: #fef2f2;
		color: #dc2626;
	}

	.action-buttons {
		display: flex;
		gap: 0.5rem;
	}

	.btn-primary {
		padding: 0.5rem 1rem;
		background: #6366f1;
		color: white;
		border: none;
		border-radius: 6px;
		cursor: pointer;
		font-size: 0.875rem;
	}

	.btn-sm {
		padding: 0.25rem 0.5rem;
		background: #f3f4f6;
		border: 1px solid #e5e7eb;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.75rem;
	}

	.btn-sm:hover {
		background: #e5e7eb;
	}

	.btn-warning {
		background: #fef3c7;
		border-color: #fcd34d;
		color: #92400e;
	}

	.btn-success {
		background: #dcfce7;
		border-color: #86efac;
		color: #166534;
	}

	.btn-danger {
		background: #fef2f2;
		border-color: #fecaca;
		color: #dc2626;
	}

	.btn-secondary {
		background: white;
		color: #6b7280;
		border: 1px solid #e5e7eb;
	}

	.assign-group-section {
		margin-top: 1.5rem;
		padding: 1.5rem;
		background: #f9fafb;
		border-radius: 8px;
	}

	.assign-group-section h3 {
		margin: 0 0 1rem;
		font-size: 1rem;
	}

	.form-row {
		display: flex;
		gap: 0.5rem;
		align-items: flex-start;
	}

	.form-row select {
		min-width: 200px;
		min-height: 100px;
	}

	/* Modals */
	.modal-overlay {
		position: fixed;
		inset: 0;
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
		min-width: 400px;
		max-width: 90vw;
	}

	.modal h3 {
		margin: 0 0 1.5rem;
	}

	.form-group {
		margin-bottom: 1rem;
	}

	.form-group label {
		display: block;
		margin-bottom: 0.5rem;
		font-weight: 500;
		color: #374151;
	}

	.form-group input,
	.form-group select {
		width: 100%;
		padding: 0.5rem;
		border: 1px solid #e5e7eb;
		border-radius: 4px;
	}

	.modal-actions {
		display: flex;
		gap: 0.5rem;
		margin-top: 1.5rem;
	}

	.modal-actions button {
		padding: 0.5rem 1rem;
		border-radius: 6px;
		cursor: pointer;
	}

	.modal-actions button:first-child {
		background: #6366f1;
		color: white;
		border: none;
	}

	.modal-actions button:first-child:disabled {
		background: #c7d2fe;
	}
</style>
