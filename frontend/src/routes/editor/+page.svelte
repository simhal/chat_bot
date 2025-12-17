<script lang="ts">
    import { auth } from '$lib/stores/auth';
    import { goto } from '$app/navigation';
    import { onMount } from 'svelte';

    const allTopics = ['macro', 'equity', 'fixed_income', 'esg'];

    function hasEditorAccess(topic: string): boolean {
        if (!$auth.user?.scopes) return false;
        if ($auth.user.scopes.includes('global:admin')) return true;
        return $auth.user.scopes.includes(`${topic}:admin`) ||
               $auth.user.scopes.includes(`${topic}:editor`);
    }

    onMount(() => {
        if (!$auth.isAuthenticated) {
            goto('/');
            return;
        }

        const firstTopic = allTopics.find(topic => hasEditorAccess(topic));
        if (firstTopic) {
            goto(`/editor/${firstTopic}`);
        } else {
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
