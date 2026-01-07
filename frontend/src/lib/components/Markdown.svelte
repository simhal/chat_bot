<script lang="ts">
    import { marked } from 'marked';
    import DOMPurify from 'dompurify';
    import { getResourceContentUrl } from '$lib/api';
    import { goto } from '$app/navigation';
    import { onMount } from 'svelte';

    export let content: string;

    let renderedContent = '';
    let containerEl: HTMLDivElement;

    // Configure marked for better rendering
    marked.setOptions({
        breaks: true, // Convert \n to <br>
        gfm: true, // GitHub Flavored Markdown
    });

    // Pre-process markdown to convert resource links to regular links with permanent URLs
    function preprocessResourceLinks(markdown: string): string {
        // Pattern: [name](resource:hash_id)
        const resourcePattern = /\[([^\]]+)\]\(resource:([a-zA-Z0-9]+)\)/g;

        return markdown.replace(resourcePattern, (match, name, hashId) => {
            // Convert to a regular markdown link with the permanent resource URL
            const contentUrl = getResourceContentUrl(hashId);
            return `[${name}](${contentUrl})`;
        });
    }

    // Pre-process markdown to convert goto links to navigation buttons
    function preprocessGotoLinks(markdown: string): string {
        // Pattern: [button text](goto:/path)
        const gotoPattern = /\[([^\]]+)\]\(goto:([^)]+)\)/g;

        return markdown.replace(gotoPattern, (match, text, path) => {
            // Convert to a styled button link with data attribute for path
            return `<a href="${path}" class="goto-button" data-goto-path="${path}">${text}</a>`;
        });
    }

    function renderMarkdown(markdown: string): string {
        // Pre-process resource links
        let processedMarkdown = preprocessResourceLinks(markdown);
        // Pre-process goto links
        processedMarkdown = preprocessGotoLinks(processedMarkdown);

        // Parse markdown to HTML
        const html = marked.parse(processedMarkdown) as string;

        // Sanitize to prevent XSS - allow our custom attributes and elements
        return DOMPurify.sanitize(html, {
            ADD_ATTR: ['data-hash-id', 'data-name', 'data-resource-type', 'target', 'data-goto-path'],
            ADD_TAGS: ['iframe']
        });
    }

    // Handle clicks on goto buttons
    function handleClick(event: MouseEvent) {
        const target = event.target as HTMLElement;
        const gotoButton = target.closest('.goto-button') as HTMLAnchorElement;

        if (gotoButton) {
            event.preventDefault();
            const path = gotoButton.dataset.gotoPath;
            if (path) {
                goto(path);
            }
        }
    }

    $: renderedContent = renderMarkdown(content);
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="markdown-content" bind:this={containerEl} on:click={handleClick}>
    {@html renderedContent}
</div>

<style>
    .markdown-content {
        line-height: 1.6;
    }

    /* Headings */
    .markdown-content :global(h1) {
        font-size: 1.8em;
        font-weight: 600;
        margin: 1em 0 0.5em;
        color: #1a1a1a;
    }

    .markdown-content :global(h2) {
        font-size: 1.5em;
        font-weight: 600;
        margin: 0.9em 0 0.4em;
        color: #1a1a1a;
    }

    .markdown-content :global(h3) {
        font-size: 1.3em;
        font-weight: 600;
        margin: 0.8em 0 0.3em;
        color: #1a1a1a;
    }

    .markdown-content :global(h4),
    .markdown-content :global(h5),
    .markdown-content :global(h6) {
        font-size: 1.1em;
        font-weight: 600;
        margin: 0.7em 0 0.3em;
        color: #1a1a1a;
    }

    /* Paragraphs */
    .markdown-content :global(p) {
        margin: 0.5em 0;
    }

    /* Links */
    .markdown-content :global(a) {
        color: #0077b5;
        text-decoration: none;
    }

    .markdown-content :global(a:hover) {
        text-decoration: underline;
    }

    /* Lists */
    .markdown-content :global(ul),
    .markdown-content :global(ol) {
        margin: 0.5em 0;
        padding-left: 2em;
    }

    .markdown-content :global(li) {
        margin: 0.25em 0;
    }

    /* Code blocks */
    .markdown-content :global(code) {
        background: rgba(0, 0, 0, 0.05);
        padding: 0.2em 0.4em;
        border-radius: 3px;
        font-family: 'Courier New', Courier, monospace;
        font-size: 0.9em;
    }

    .markdown-content :global(pre) {
        background: #f6f8fa;
        padding: 1em;
        border-radius: 6px;
        overflow-x: auto;
        margin: 1em 0;
    }

    .markdown-content :global(pre code) {
        background: none;
        padding: 0;
    }

    /* Blockquotes */
    .markdown-content :global(blockquote) {
        border-left: 4px solid #ddd;
        padding-left: 1em;
        margin: 1em 0;
        color: #666;
        font-style: italic;
    }

    /* Tables */
    .markdown-content :global(table) {
        border-collapse: collapse;
        width: 100%;
        margin: 1em 0;
    }

    .markdown-content :global(th),
    .markdown-content :global(td) {
        border: 1px solid #ddd;
        padding: 0.5em;
        text-align: left;
    }

    .markdown-content :global(th) {
        background: #f6f8fa;
        font-weight: 600;
    }

    /* Horizontal rule */
    .markdown-content :global(hr) {
        border: none;
        border-top: 1px solid #ddd;
        margin: 1.5em 0;
    }

    /* Images */
    .markdown-content :global(img) {
        max-width: 100%;
        height: auto;
        border-radius: 4px;
        margin: 0.5em 0;
    }

    /* Strong and emphasis */
    .markdown-content :global(strong) {
        font-weight: 600;
    }

    .markdown-content :global(em) {
        font-style: italic;
    }

    /* Resource embed styles */
    .markdown-content :global(.resource-link-placeholder) {
        display: inline-block;
    }

    .markdown-content :global(.resource-loading) {
        color: #6b7280;
        font-style: italic;
    }

    .markdown-content :global(.resource-error) {
        color: #dc2626;
        font-size: 0.9em;
    }

    .markdown-content :global(.resource-embed-image) {
        max-width: 100%;
        height: auto;
        border-radius: 8px;
        margin: 1rem 0;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    }

    .markdown-content :global(.resource-embed-pdf) {
        padding: 1rem;
        background: #f8f9fa;
        border-radius: 8px;
        border-left: 4px solid #3b82f6;
        margin: 1rem 0;
    }

    .markdown-content :global(.resource-pdf-link) {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        color: #3b82f6;
        text-decoration: none;
        font-weight: 500;
    }

    .markdown-content :global(.resource-pdf-link:hover) {
        text-decoration: underline;
    }

    .markdown-content :global(.inline-table-container) {
        width: 100%;
        overflow-x: auto;
        margin: 1rem 0;
    }

    .markdown-content :global(.inline-data-table) {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.875rem;
        background: white;
    }

    .markdown-content :global(.inline-data-table th) {
        background: #f8fafc;
        border-bottom: 2px solid #e2e8f0;
        padding: 0.75rem 1rem;
        text-align: left;
        font-weight: 600;
        color: #334155;
        white-space: nowrap;
        cursor: pointer;
        user-select: none;
    }

    .markdown-content :global(.inline-data-table th:hover) {
        background: #f1f5f9;
    }

    .markdown-content :global(.inline-data-table th .sort-indicator) {
        margin-left: 0.5rem;
        font-size: 0.7rem;
        color: #cbd5e1;
    }

    .markdown-content :global(.inline-data-table th .sort-indicator::after) {
        content: '⇅';
    }

    .markdown-content :global(.inline-data-table th.sorted-asc .sort-indicator::after) {
        content: '▲';
        color: #3b82f6;
    }

    .markdown-content :global(.inline-data-table th.sorted-desc .sort-indicator::after) {
        content: '▼';
        color: #3b82f6;
    }

    .markdown-content :global(.inline-data-table td) {
        padding: 0.625rem 1rem;
        border-bottom: 1px solid #f1f5f9;
        color: #475569;
    }

    .markdown-content :global(.inline-data-table tbody tr:hover) {
        background: #f8fafc;
    }

    .markdown-content :global(.inline-data-table tbody tr:nth-child(even)) {
        background: #fafbfc;
    }

    .markdown-content :global(.inline-data-table tbody tr:nth-child(even):hover) {
        background: #f1f5f9;
    }

    .markdown-content :global(.resource-embed-table-fallback) {
        padding: 0.75rem 1rem;
        background: #f9fafb;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        margin: 1rem 0;
    }

    .markdown-content :global(.resource-embed-table-fallback a) {
        color: #3b82f6;
        text-decoration: none;
    }

    .markdown-content :global(.resource-embed-table-fallback a:hover) {
        text-decoration: underline;
    }

    .markdown-content :global(.resource-embed-text) {
        background: #f8f9fa;
        border-left: 4px solid #6b7280;
        padding: 1rem;
        margin: 1rem 0;
        font-style: normal;
    }

    .markdown-content :global(.resource-embed-text cite) {
        display: block;
        font-weight: 600;
        margin-bottom: 0.5rem;
        font-style: normal;
    }

    .markdown-content :global(.resource-text-link) {
        color: #3b82f6;
        text-decoration: none;
    }

    .markdown-content :global(.resource-text-link:hover) {
        text-decoration: underline;
    }

    .markdown-content :global(.resource-embed-link) {
        display: inline-flex;
        align-items: center;
        gap: 0.25rem;
        color: #3b82f6;
        text-decoration: none;
        padding: 0.25rem 0.5rem;
        background: #eff6ff;
        border-radius: 4px;
    }

    .markdown-content :global(.resource-embed-link:hover) {
        background: #dbeafe;
        text-decoration: none;
    }

    .markdown-content :global(.resource-embed-html) {
        padding: 1rem;
        background: #f0fdf4;
        border-radius: 8px;
        border-left: 4px solid #22c55e;
        margin: 1rem 0;
    }

    .markdown-content :global(.resource-html-link) {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        color: #16a34a;
        text-decoration: none;
        font-weight: 500;
    }

    .markdown-content :global(.resource-html-link:hover) {
        text-decoration: underline;
    }

    /* Navigation goto buttons */
    .markdown-content :global(.goto-button) {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 1rem;
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
        color: white !important;
        text-decoration: none !important;
        border-radius: 6px;
        font-weight: 500;
        font-size: 0.875rem;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 2px 4px rgba(59, 130, 246, 0.3);
        margin: 0.25rem 0.25rem 0.25rem 0;
    }

    .markdown-content :global(.goto-button:hover) {
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
        box-shadow: 0 4px 8px rgba(59, 130, 246, 0.4);
        transform: translateY(-1px);
        text-decoration: none !important;
    }

    .markdown-content :global(.goto-button:active) {
        transform: translateY(0);
        box-shadow: 0 2px 4px rgba(59, 130, 246, 0.3);
    }

    .markdown-content :global(.goto-button::before) {
        content: '→';
        font-size: 1rem;
    }
</style>
