<script lang="ts">
    import { marked } from 'marked';
    import DOMPurify from 'dompurify';
    import { onMount } from 'svelte';

    export let content: string;

    let renderedContent = '';

    // Configure marked for better rendering
    marked.setOptions({
        breaks: true, // Convert \n to <br>
        gfm: true, // GitHub Flavored Markdown
    });

    function renderMarkdown(markdown: string): string {
        // Parse markdown to HTML
        const html = marked.parse(markdown) as string;
        // Sanitize to prevent XSS
        return DOMPurify.sanitize(html);
    }

    $: renderedContent = renderMarkdown(content);
</script>

<div class="markdown-content">
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
</style>
