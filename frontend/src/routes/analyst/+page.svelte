<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { goto } from '$app/navigation';
    import { onMount } from 'svelte';
    import { getTopics } from '$lib/api';

    function hasTopicAccess(topic: string): boolean {
        if (!$auth.user?.scopes) return false;
        // Global admin can access all topics
        if ($auth.user.scopes.includes('global:admin')) return true;
        // Or analyst role grants access
        return $auth.user.scopes.includes(`${topic}:analyst`);
    }

    onMount(async () => {
        if (!$auth.isAuthenticated) {
            goto('/');
            return;
        }

        try {
            // Load topics from database
            const dbTopics = await getTopics(); // Show all topics
            const sortedTopics = dbTopics.sort((a, b) => a.sort_order - b.sort_order);

            // Find first available topic for user
            const firstTopic = sortedTopics.find(topic => hasTopicAccess(topic.slug));

            if (firstTopic) {
                // Redirect to first available topic
                goto(`/analyst/${firstTopic.slug}`);
            } else {
                // No analyst permissions, redirect home
                goto('/');
            }
        } catch (e) {
            console.error('Error loading topics:', e);
            goto('/');
        }
    });
</script>

<div class="analyst-container">
    <div class="loading">
        Redirecting to analyst dashboard...
    </div>
</div>

<style>
    :global(body) {
        background: #fafafa;
    }

    .analyst-container {
        max-width: 1200px;
        margin: 0 auto;
        background: white;
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
