<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { goto } from '$app/navigation';
    import { onMount } from 'svelte';

    const allTopics = ['macro', 'equity', 'fixed_income', 'esg'];

    function hasEditorAccess(topic: string, scopes: string[]): boolean {
        if (!scopes.length) return false;
        // Only show for users with explicit editor role for that topic
        return scopes.includes(`${topic}:editor`);
    }

    onMount(() => {
        if (!$auth.isAuthenticated) {
            goto('/');
            return;
        }

        const scopes = $auth.user?.scopes || [];
        const firstTopic = allTopics.find(topic => hasEditorAccess(topic, scopes));
        if (firstTopic) {
            goto(`/editor/${firstTopic}`);
        } else {
            // User has no editor access to any topic
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
