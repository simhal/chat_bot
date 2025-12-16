<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { goto } from '$app/navigation';
    import { onMount } from 'svelte';

    interface TopicCard {
        id: string;
        label: string;
        description: string;
        requiredScope: string;
        icon: string;
    }

    const allTopics: TopicCard[] = [
        {
            id: 'macro',
            label: 'Macroeconomic Research',
            description: 'Economic indicators, central bank policy, and global macro trends',
            requiredScope: 'macro_analyst',
            icon: 'MACRO'
        },
        {
            id: 'equity',
            label: 'Equity Research',
            description: 'Stock markets, company analysis, and equity valuations',
            requiredScope: 'equity_analyst',
            icon: 'EQUITY'
        },
        {
            id: 'fixed_income',
            label: 'Fixed Income Research',
            description: 'Bonds, yields, credit markets, and fixed income securities',
            requiredScope: 'fi_analyst',
            icon: 'FI'
        },
        {
            id: 'esg',
            label: 'ESG Research',
            description: 'Environmental, social, and governance factors in investing',
            requiredScope: 'esg_analyst',
            icon: 'ESG'
        }
    ];

    let availableTopics: TopicCard[] = [];
    let isAnalyst = false;

    $: {
        if ($auth.user?.scopes) {
            // Filter topics based on user's analyst scopes (admin doesn't get automatic access)
            availableTopics = allTopics.filter(topic =>
                $auth.user?.scopes?.includes(topic.requiredScope)
            );
            isAnalyst = availableTopics.length > 0;
        }
    }

    // Redirect if not an analyst
    $: if ($auth.isAuthenticated && !isAnalyst) {
        goto('/');
    }

    function navigateToTopic(topicId: string) {
        goto(`/analyst/${topicId}`);
    }

    onMount(() => {
        if (!$auth.isAuthenticated) {
            goto('/');
        }
    });
</script>

<div class="analyst-container">
    <header class="analyst-header">
        <div>
            <h1>Analyst Dashboard</h1>
            <p class="subtitle">Manage and create research content</p>
        </div>
    </header>

    {#if availableTopics.length === 0}
        <div class="empty-state">
            <h2>No Access</h2>
            <p>You do not have analyst permissions for any research areas.</p>
            <p>Please contact an administrator to request access.</p>
        </div>
    {:else}
        <div class="topics-grid">
            {#each availableTopics as topic}
                <button class="topic-card" on:click={() => navigateToTopic(topic.id)}>
                    <div class="topic-icon">{topic.icon}</div>
                    <h3>{topic.label}</h3>
                    <p>{topic.description}</p>
                    <div class="topic-action">
                        View Content →
                    </div>
                </button>
            {/each}
        </div>

        {#if $auth.user?.scopes?.includes('admin')}
            <div class="admin-notice">
                <strong>Note:</strong> You also have admin access. Visit the <a href="/admin">Admin Panel</a> for user management and system configuration.
            </div>
        {/if}
    {/if}
</div>

<style>
    .analyst-container {
        max-width: 1200px;
        margin: 0 auto;
        padding: 3rem 2rem;
        background: #fafafa;
        min-height: 100vh;
    }

    .analyst-header {
        margin-bottom: 3rem;
        padding-bottom: 1.5rem;
        border-bottom: 1px solid #e0e0e0;
    }

    .analyst-header h1 {
        margin: 0 0 0.5rem 0;
        color: #1a1a1a;
        font-size: 1.75rem;
        font-weight: 600;
        letter-spacing: -0.01em;
    }

    .subtitle {
        margin: 0;
        color: #6b7280;
        font-size: 0.95rem;
        font-weight: 400;
    }

    .empty-state {
        text-align: center;
        padding: 4rem 2rem;
        background: white;
        border-radius: 4px;
        border: 1px solid #e5e7eb;
    }

    .empty-state h2 {
        color: #1a1a1a;
        margin-bottom: 1rem;
        font-weight: 600;
    }

    .empty-state p {
        color: #6b7280;
        margin-bottom: 0.5rem;
    }

    .topics-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
        gap: 1.5rem;
        margin-bottom: 2rem;
    }

    .topic-card {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        padding: 2rem 1.5rem;
        text-align: left;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .topic-card:hover {
        border-color: #3b82f6;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    }

    .topic-icon {
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.05em;
        color: #3b82f6;
        margin-bottom: 1rem;
        padding: 0.25rem 0.5rem;
        background: #eff6ff;
        border-radius: 2px;
        display: inline-block;
    }

    .topic-card h3 {
        margin: 0 0 0.5rem 0;
        color: #1a1a1a;
        font-size: 1.125rem;
        font-weight: 600;
    }

    .topic-card p {
        color: #6b7280;
        font-size: 0.875rem;
        line-height: 1.5;
        margin-bottom: 1rem;
    }

    .topic-action {
        color: #3b82f6;
        font-weight: 500;
        font-size: 0.875rem;
    }

    .admin-notice {
        padding: 1rem 1.25rem;
        background: #f9fafb;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        color: #374151;
        line-height: 1.5;
        font-size: 0.875rem;
    }

    .admin-notice strong {
        color: #1a1a1a;
    }

    .admin-notice a {
        color: #3b82f6;
        text-decoration: none;
        font-weight: 500;
    }

    .admin-notice a:hover {
        text-decoration: underline;
    }
</style>
