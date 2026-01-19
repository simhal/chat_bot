<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { getUserProfile } from '$lib/api';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { navigationContext, type SectionName } from '$lib/stores/navigation';

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

	let userProfile: UserProfile | null = null;
	let loading = true;
	let error = '';

	// Redirect if not authenticated (only in browser)
	$: if (browser && !$auth.isAuthenticated) {
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

	function formatDate(dateString: string) {
		return new Date(dateString).toLocaleDateString('en-US', {
			year: 'numeric',
			month: 'long',
			day: 'numeric'
		});
	}

	onMount(() => {
		// Set navigation context for user_profile section (from sections.json)
		navigationContext.setSection('user_profile' as SectionName);
		loadUserProfile();
	});
</script>

<div class="profile-container" data-testid="profile-page">
	<nav class="tabs">
		<a href="/user/profile" class="tab active">Profile Info</a>
		<a href="/user/settings" class="tab">Settings</a>
	</nav>

	{#if error}
		<div class="error-message">{error}</div>
	{/if}

	{#if loading}
		<div class="loading">Loading profile...</div>
	{:else if userProfile}
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
						<span class="info-value" data-testid="user-name">
							{#if userProfile.name || userProfile.surname}
								{userProfile.name || ''} {userProfile.surname || ''}
							{:else}
								Not set
							{/if}
						</span>
					</div>

					<div class="info-row">
						<span class="info-label">Email:</span>
						<span class="info-value" data-testid="user-email">{userProfile.email}</span>
					</div>

					<div class="info-row" data-testid="access-stats">
						<span class="info-label">Member Since:</span>
						<span class="info-value">{formatDate(userProfile.created_at)}</span>
					</div>

					<div class="info-row" data-testid="user-groups">
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

	.loading {
		text-align: center;
		padding: 3rem;
		color: #6b7280;
	}

	.profile-content {
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
</style>
