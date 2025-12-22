<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { goto } from '$app/navigation';
    import { onMount } from 'svelte';
    import { getTopics } from '$lib/api';

    // Shared localStorage key for topic persistence across analyst, editor, admin
    const SELECTED_TOPIC_KEY = 'selected_topic';

    function getSavedTopic(): string | null {
        if (typeof localStorage !== 'undefined') {
            return localStorage.getItem(SELECTED_TOPIC_KEY);
        }
        return null;
    }

    function hasEditorAccess(topic: string, scopes: string[]): boolean {
        if (!scopes.length) return false;
        // Global admin can access all topics
        if (scopes.includes('global:admin')) return true;
        // Or users with explicit editor role for that topic
        return scopes.includes(`${topic}:editor`);
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

            const scopes = $auth.user?.scopes || [];

            // Check for saved topic first
            const savedTopic = getSavedTopic();
            if (savedTopic && sortedTopics.some(t => t.slug === savedTopic && hasEditorAccess(t.slug, scopes))) {
                goto(`/editor/${savedTopic}`);
                return;
            }

            const firstTopic = sortedTopics.find(topic => hasEditorAccess(topic.slug, scopes));
            if (firstTopic) {
                goto(`/editor/${firstTopic.slug}`);
            } else {
                // User has no editor access to any topic
                goto('/');
            }
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
