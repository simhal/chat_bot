<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { goto } from '$app/navigation';
    import { onMount } from 'svelte';
    import { getEntitledTopics } from '$lib/api';

    // Shared localStorage key for topic persistence across analyst, editor, admin
    const SELECTED_TOPIC_KEY = 'selected_topic';

    function getSavedTopic(): string | null {
        if (typeof localStorage !== 'undefined') {
            return localStorage.getItem(SELECTED_TOPIC_KEY);
        }
        return null;
    }

    onMount(async () => {
        if (!$auth.isAuthenticated) {
            goto('/');
            return;
        }

        try {
            // Load topics user has editor access to (backend filters by entitlements)
            const entitledTopics = await getEntitledTopics('editor');
            const sortedTopics = entitledTopics.sort((a, b) => a.sort_order - b.sort_order);

            if (sortedTopics.length === 0) {
                // No editor permissions for any topic, redirect home
                goto('/');
                return;
            }

            // Check for saved topic first
            const savedTopic = getSavedTopic();
            if (savedTopic && sortedTopics.some(t => t.slug === savedTopic)) {
                goto(`/editor/${savedTopic}`);
                return;
            }

            // Redirect to first available topic
            goto(`/editor/${sortedTopics[0].slug}`);
        } catch (e) {
            console.error('Error loading topics:', e);
            goto('/');
        }
    });
</script>

<div class="editor-container">
    <div class="loading">Redirecting to editor dashboard...</div>
</div>

<style>
    .editor-container { max-width: 1200px; margin: 0 auto; background: white; min-height: 100vh; padding: 2rem; }
    .loading { text-align: center; padding: 3rem; color: #666; }
</style>
