<script lang="ts">
    import { marked } from 'marked';
    import DOMPurify from 'dompurify';
    import { onMount } from 'svelte';
    import { getResourceContentUrl } from '$lib/api';

    export let content: string;

    let renderedContent = '';
    let containerElement: HTMLElement;
    let pendingScripts: string[] = [];

    // Configure marked for better rendering
    marked.setOptions({
        breaks: true, // Convert \n to <br>
        gfm: true, // GitHub Flavored Markdown
    });

    // Resource type icons
    const resourceIcons: Record<string, string> = {
        image: '🖼️',
        pdf: '📄',
        text: '📝',
        table: '📊',
        excel: '📊',
        csv: '📊',
        zip: '📦',
        default: '📎'
    };

    // Pre-process markdown to convert resource links to HTML embeds
    function preprocessResourceLinks(markdown: string): string {
        // Pattern: [name](resource:hash_id)
        const resourcePattern = /\[([^\]]+)\]\(resource:([a-zA-Z0-9]+)\)/g;

        return markdown.replace(resourcePattern, (match, name, hashId) => {
            // Return a placeholder span that will be enhanced after render
            const escapedName = name.replace(/"/g, '&quot;');
            return `<span class="resource-link-placeholder" data-hash-id="${hashId}" data-name="${escapedName}">` +
                   `<span class="resource-loading">📎 ${escapedName}</span>` +
                   `</span>`;
        });
    }

    function renderMarkdown(markdown: string): string {
        // Pre-process resource links
        const processedMarkdown = preprocessResourceLinks(markdown);

        // Parse markdown to HTML
        const html = marked.parse(processedMarkdown) as string;

        // Sanitize to prevent XSS - allow our custom attributes and elements
        return DOMPurify.sanitize(html, {
            ADD_ATTR: ['data-hash-id', 'data-name', 'data-resource-type', 'target'],
            ADD_TAGS: ['iframe']
        });
    }

    // Fetch resource info and update placeholder elements
    async function enhanceResourceLinks() {
        if (!containerElement) return;

        // Reset pending scripts for this render
        pendingScripts = [];

        const placeholders = containerElement.querySelectorAll('.resource-link-placeholder');

        for (const placeholder of placeholders) {
            const hashId = placeholder.getAttribute('data-hash-id');
            const name = placeholder.getAttribute('data-name') || 'Resource';

            if (!hashId) continue;

            try {
                // Fetch resource info
                const response = await fetch(`${getResourceContentUrl(hashId)}/info`);
                if (!response.ok) {
                    // Resource not found - show as broken link
                    placeholder.innerHTML = `<span class="resource-error">⚠️ ${name} (not found)</span>`;
                    continue;
                }

                const info = await response.json();
                const resourceType = info.resource_type || 'unknown';
                const contentUrl = getResourceContentUrl(hashId);
                const icon = resourceIcons[resourceType] || resourceIcons.default;

                // Generate appropriate HTML based on resource type
                let embedHtml = '';

                switch (resourceType) {
                    case 'image':
                        embedHtml = `<img src="${contentUrl}" alt="${name}" class="resource-embed-image" loading="lazy" />`;
                        break;
                    case 'pdf':
                        embedHtml = `<div class="resource-embed-pdf">
                            <a href="${contentUrl}" target="_blank" rel="noopener" class="resource-pdf-link">
                                ${icon} ${name}
                            </a>
                        </div>`;
                        break;
                    case 'table':
                        // Fetch embeddable HTML fragment from backend
                        try {
                            const embedUrl = `${getResourceContentUrl(hashId)}/embed`;
                            const embedResponse = await fetch(embedUrl);
                            if (embedResponse.ok) {
                                // Get the complete embeddable HTML (styles + table + script)
                                const fullHtml = await embedResponse.text();
                                // Extract and separate the script for later execution
                                const scriptMatch = fullHtml.match(/<script>([\s\S]*?)<\/script>/);
                                const scriptContent = scriptMatch ? scriptMatch[1] : '';
                                // Store script for post-render execution
                                if (scriptContent) {
                                    pendingScripts.push(scriptContent);
                                }
                                // Insert HTML without the script tag (script will be executed after DOM update)
                                embedHtml = fullHtml.replace(/<script>[\s\S]*?<\/script>/, '');
                            } else {
                                embedHtml = `<div class="resource-embed-table-fallback">
                                    <a href="${contentUrl}" target="_blank" rel="noopener">${icon} ${name}</a>
                                </div>`;
                            }
                        } catch (e) {
                            embedHtml = `<div class="resource-embed-table-fallback">
                                <a href="${contentUrl}" target="_blank" rel="noopener">${icon} ${name}</a>
                            </div>`;
                        }
                        break;
                    case 'text':
                        embedHtml = `<blockquote class="resource-embed-text">
                            <cite>${icon} ${name}</cite>
                            <a href="${contentUrl}" target="_blank" rel="noopener" class="resource-text-link">View Full Text</a>
                        </blockquote>`;
                        break;
                    default:
                        embedHtml = `<a href="${contentUrl}" target="_blank" rel="noopener" class="resource-embed-link">
                            ${icon} ${name}
                        </a>`;
                }

                placeholder.innerHTML = embedHtml;
                placeholder.setAttribute('data-resource-type', resourceType);

            } catch (error) {
                console.error(`Failed to load resource ${hashId}:`, error);
                placeholder.innerHTML = `<span class="resource-error">⚠️ ${name} (error loading)</span>`;
            }
        }

        // Execute pending scripts for embedded tables after DOM update
        if (pendingScripts.length > 0) {
            // Use setTimeout to ensure DOM is fully updated before running scripts
            setTimeout(() => {
                for (const scriptContent of pendingScripts) {
                    try {
                        // Execute the script in global scope
                        const scriptFn = new Function(scriptContent);
                        scriptFn();
                    } catch (e) {
                        console.error('Failed to execute embedded table script:', e);
                    }
                }
                pendingScripts = [];
            }, 10);
        }
    }

    $: renderedContent = renderMarkdown(content);

    // Enhance resource links after content is rendered
    $: if (renderedContent && containerElement) {
        // Use setTimeout to ensure DOM is updated
        setTimeout(enhanceResourceLinks, 0);
    }

    // Add global sorting function for inline tables
    onMount(() => {
        // Define the sorting function globally
        (window as any).sortInlineTable = function(tableId: string, columnIndex: number) {
            const table = document.getElementById(tableId);
            if (!table) return;

            const tbody = table.querySelector('tbody');
            const headers = table.querySelectorAll('th');
            if (!tbody) return;

            const rows = Array.from(tbody.querySelectorAll('tr'));
            const header = headers[columnIndex];

            // Determine sort direction
            const isAsc = header.classList.contains('sorted-asc');
            const newDirection = isAsc ? 'desc' : 'asc';

            // Clear all sort classes
            headers.forEach(th => th.classList.remove('sorted-asc', 'sorted-desc'));
            header.classList.add(newDirection === 'asc' ? 'sorted-asc' : 'sorted-desc');

            // Sort rows
            rows.sort((a, b) => {
                const aVal = a.cells[columnIndex]?.textContent?.trim() || '';
                const bVal = b.cells[columnIndex]?.textContent?.trim() || '';

                // Try numeric comparison
                const aNum = parseFloat(aVal.replace(/[,\s]/g, ''));
                const bNum = parseFloat(bVal.replace(/[,\s]/g, ''));

                if (!isNaN(aNum) && !isNaN(bNum)) {
                    return newDirection === 'asc' ? aNum - bNum : bNum - aNum;
                }

                // String comparison
                return newDirection === 'asc'
                    ? aVal.localeCompare(bVal)
                    : bVal.localeCompare(aVal);
            });

            // Re-append sorted rows
            rows.forEach(row => tbody.appendChild(row));
        };
    });
</script>

<div class="markdown-content" bind:this={containerElement}>
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
</style>
