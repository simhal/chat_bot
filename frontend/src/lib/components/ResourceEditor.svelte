<script lang="ts">
    import { createEventDispatcher } from 'svelte';
    import { uploadFileResource, createTextResource, createTableResource, linkResourceToArticle, unlinkResourceFromArticle, deleteResource, type Resource, type ResourceDetail } from '$lib/api';

    // Props
    export let resources: Resource[] = [];
    export let articleId: number | undefined = undefined;
    export let groupId: number | undefined = undefined;
    export let groupName: string | undefined = undefined;
    export let loading: boolean = false;
    export let showDeleteButton: boolean = true;
    export let showUnlinkButton: boolean = true;

    const dispatch = createEventDispatcher<{
        refresh: void;
        error: string;
    }>();

    // Pending resource for metadata entry
    interface PendingResource {
        type: 'file' | 'table' | 'text';
        file?: File;
        tableData?: { columns: string[]; data: any[][] };
        textContent?: string;
        suggestedName: string;
    }

    // Resource metadata form
    interface ResourceMetadata {
        title: string;
        description: string;
        reference: string;
        weblink: string;
        source: string;
    }

    let isDragging = false;
    let uploadProgress = '';
    let error = '';

    // Metadata popup state
    let showMetadataModal = false;
    let pendingResource: PendingResource | null = null;
    let resourceMetadata: ResourceMetadata = {
        title: '',
        description: '',
        reference: '',
        weblink: '',
        source: ''
    };
    let metadataSaving = false;

    // Drag and drop handlers
    function handleDragOver(e: DragEvent) {
        e.preventDefault();
        isDragging = true;
    }

    function handleDragLeave(e: DragEvent) {
        e.preventDefault();
        isDragging = false;
    }

    async function handleDrop(e: DragEvent) {
        e.preventDefault();
        isDragging = false;

        const files = e.dataTransfer?.files;
        if (!files || files.length === 0) return;

        // Only process first file for metadata entry
        const file = files[0];
        openMetadataModal({
            type: 'file',
            file: file,
            suggestedName: file.name.replace(/\.[^/.]+$/, '')
        });
    }

    async function handleFileSelect(e: Event) {
        const input = e.target as HTMLInputElement;
        if (!input.files || input.files.length === 0) return;

        const file = input.files[0];
        openMetadataModal({
            type: 'file',
            file: file,
            suggestedName: file.name.replace(/\.[^/.]+$/, '')
        });
        input.value = ''; // Reset input
    }

    // Paste handler for clipboard content
    async function handlePaste(e: ClipboardEvent) {
        e.preventDefault();

        const clipboardData = e.clipboardData;
        if (!clipboardData) return;

        // IMPORTANT: Check for HTML content FIRST (Excel tables, rich text)
        // Excel puts both image and HTML on clipboard - we want the HTML table data
        const htmlContent = clipboardData.getData('text/html');
        if (htmlContent && containsTable(htmlContent)) {
            const tableData = parseHtmlTable(htmlContent);
            if (tableData && tableData.data.length > 0) {
                openMetadataModal({
                    type: 'table',
                    tableData: tableData,
                    suggestedName: `Pasted Table ${new Date().toLocaleString()}`
                });
                return;
            }
        }

        // Check for plain text that looks like TSV (tab-separated values from Excel)
        const textContent = clipboardData.getData('text/plain');
        if (textContent && looksLikeTsvData(textContent)) {
            const tableData = parseTsv(textContent);
            if (tableData && tableData.data.length > 0) {
                openMetadataModal({
                    type: 'table',
                    tableData: tableData,
                    suggestedName: `Pasted Table ${new Date().toLocaleString()}`
                });
                return;
            }
        }

        // Check for files (images, etc.) - after table checks
        if (clipboardData.files && clipboardData.files.length > 0) {
            const file = clipboardData.files[0];
            openMetadataModal({
                type: 'file',
                file: file,
                suggestedName: `Pasted ${file.type.split('/')[0]} ${new Date().toLocaleString()}`
            });
            return;
        }

        // Fall back to plain text (non-table text snippets)
        if (textContent && textContent.trim().length >= 50) {
            openMetadataModal({
                type: 'text',
                textContent: textContent,
                suggestedName: `Text Snippet ${new Date().toLocaleString()}`
            });
        } else if (textContent && textContent.trim().length > 0) {
            error = 'Text too short to create resource (minimum 50 characters)';
            dispatch('error', error);
        }
    }

    // Open metadata modal
    function openMetadataModal(pending: PendingResource) {
        pendingResource = pending;
        resourceMetadata = {
            title: pending.suggestedName,
            description: '',
            reference: '',
            weblink: '',
            source: ''
        };
        showMetadataModal = true;
    }

    // Close metadata modal
    function closeMetadataModal() {
        showMetadataModal = false;
        pendingResource = null;
        resourceMetadata = {
            title: '',
            description: '',
            reference: '',
            weblink: '',
            source: ''
        };
    }

    // Save resource with metadata
    async function saveResourceWithMetadata() {
        if (!pendingResource || !resourceMetadata.title.trim()) return;

        try {
            metadataSaving = true;
            error = '';

            // Build description with metadata
            const descriptionParts = [];
            if (resourceMetadata.description) descriptionParts.push(resourceMetadata.description);
            if (resourceMetadata.reference) descriptionParts.push(`Reference: ${resourceMetadata.reference}`);
            if (resourceMetadata.weblink) descriptionParts.push(`Link: ${resourceMetadata.weblink}`);
            if (resourceMetadata.source) descriptionParts.push(`Source: ${resourceMetadata.source}`);
            const fullDescription = descriptionParts.join(' | ');

            let resource: ResourceDetail;

            if (pendingResource.type === 'file' && pendingResource.file) {
                resource = await uploadFileResource(
                    pendingResource.file,
                    resourceMetadata.title,
                    articleId,
                    groupId,
                    fullDescription,
                    groupName  // Pass groupName for backend resolution
                );
                // If we have articleId but uploadFileResource didn't link it (groupId case)
                if (articleId && groupId) {
                    await linkResourceToArticle(resource.id, articleId);
                }
            } else if (pendingResource.type === 'table' && pendingResource.tableData) {
                resource = await createTableResource(
                    resourceMetadata.title,
                    pendingResource.tableData,
                    groupId,
                    fullDescription,
                    undefined,  // columnTypes
                    groupName  // Pass groupName for backend resolution
                );
                if (articleId) {
                    await linkResourceToArticle(resource.id, articleId);
                }
            } else if (pendingResource.type === 'text' && pendingResource.textContent) {
                resource = await createTextResource(
                    resourceMetadata.title,
                    pendingResource.textContent,
                    groupId,
                    fullDescription,
                    groupName  // Pass groupName for backend resolution
                );
                if (articleId) {
                    await linkResourceToArticle(resource.id, articleId);
                }
            }

            closeMetadataModal();
            dispatch('refresh');
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to save resource';
            dispatch('error', error);
        } finally {
            metadataSaving = false;
        }
    }

    // Check if HTML contains a table
    function containsTable(html: string): boolean {
        return /<table[\s>]/i.test(html);
    }

    // Check if text looks like tab-separated values
    function looksLikeTsvData(text: string): boolean {
        const lines = text.trim().split('\n');
        if (lines.length < 2) return false;

        // Check if most lines have tabs (indicating columns)
        const linesWithTabs = lines.filter(line => line.includes('\t'));
        return linesWithTabs.length > lines.length * 0.5;
    }

    // Parse HTML table to structured data
    function parseHtmlTable(html: string): { columns: string[]; data: any[][] } | null {
        try {
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const table = doc.querySelector('table');

            if (!table) return null;

            const rows = Array.from(table.querySelectorAll('tr'));
            if (rows.length === 0) return null;

            // First row as headers
            const headerRow = rows[0];
            const columns = Array.from(headerRow.querySelectorAll('th, td')).map(cell =>
                cell.textContent?.trim() || ''
            );

            // Rest as data
            const data: any[][] = [];
            for (let i = 1; i < rows.length; i++) {
                const cells = Array.from(rows[i].querySelectorAll('td, th'));
                const rowData = cells.map(cell => {
                    const text = cell.textContent?.trim() || '';
                    // Try to parse as number
                    const num = parseFloat(text.replace(/[,\s]/g, ''));
                    return !isNaN(num) && text !== '' ? num : text;
                });
                if (rowData.some(v => v !== '')) {
                    data.push(rowData);
                }
            }

            // If no headers were found (all empty), use column indices
            const finalColumns = columns.every(c => c === '')
                ? columns.map((_, i) => `Column ${i + 1}`)
                : columns;

            return { columns: finalColumns, data };
        } catch (e) {
            console.error('Failed to parse HTML table:', e);
            return null;
        }
    }

    // Parse TSV (tab-separated values) to structured data
    function parseTsv(text: string): { columns: string[]; data: any[][] } | null {
        try {
            const lines = text.trim().split('\n');
            if (lines.length < 2) return null;

            const columns = lines[0].split('\t').map(c => c.trim());
            const data: any[][] = [];

            for (let i = 1; i < lines.length; i++) {
                const cells = lines[i].split('\t');
                const rowData = cells.map(cell => {
                    const text = cell.trim();
                    const num = parseFloat(text.replace(/[,\s]/g, ''));
                    return !isNaN(num) && text !== '' ? num : text;
                });
                if (rowData.some(v => v !== '')) {
                    data.push(rowData);
                }
            }

            return { columns, data };
        } catch (e) {
            console.error('Failed to parse TSV:', e);
            return null;
        }
    }

    async function handleRemoveResource(resource: Resource) {
        const action = articleId && showUnlinkButton ? 'unlink from this article' : 'delete';
        if (!confirm(`${articleId && showUnlinkButton ? 'Remove' : 'Delete'} "${resource.name}"${articleId && showUnlinkButton ? ' from this article' : ''}?`)) return;

        try {
            error = '';
            if (articleId && showUnlinkButton) {
                // Unlink from article (not delete the resource itself)
                await unlinkResourceFromArticle(resource.id, articleId);
            } else {
                // Delete the resource
                await deleteResource(resource.id);
            }
            dispatch('refresh');
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to remove resource';
            dispatch('error', error);
        }
    }

    function getStatusColor(status: string): string {
        switch (status) {
            case 'published': return '#10b981';
            case 'editor': return '#f59e0b';
            case 'draft':
            default: return '#6b7280';
        }
    }

    function getResourceIcon(type: string): string {
        const icons: Record<string, string> = {
            'image': '🖼️',
            'pdf': '📄',
            'text': '📝',
            'excel': '📊',
            'zip': '📦',
            'csv': '📋',
            'table': '📑',
            'timeseries': '📈'
        };
        return icons[type] || '📎';
    }

    function parseResourceDescription(description: string | null): { desc: string; reference: string; weblink: string; source: string } {
        if (!description) return { desc: '', reference: '', weblink: '', source: '' };

        const parts = description.split(' | ');
        let desc = '', reference = '', weblink = '', source = '';

        for (const part of parts) {
            if (part.startsWith('Reference: ')) {
                reference = part.replace('Reference: ', '');
            } else if (part.startsWith('Link: ')) {
                weblink = part.replace('Link: ', '');
            } else if (part.startsWith('Source: ')) {
                source = part.replace('Source: ', '');
            } else {
                desc = part;
            }
        }

        return { desc, reference, weblink, source };
    }
</script>

<div class="resource-editor">
    <!-- Drop Zone with Paste Support -->
    <div
        class="drop-zone"
        class:dragging={isDragging}
        on:dragover={handleDragOver}
        on:dragleave={handleDragLeave}
        on:drop={handleDrop}
        on:paste={handlePaste}
        role="button"
        tabindex="0"
    >
        {#if uploadProgress}
            <div class="upload-progress">
                <div class="spinner-small"></div>
                <span>{uploadProgress}</span>
            </div>
        {:else}
            <div class="drop-zone-content">
                <span class="drop-icon">📁</span>
                <p>Drag & drop files or paste content here</p>
                <p class="drop-hint">or</p>
                <label class="file-select-btn">
                    Browse Files
                    <input
                        type="file"
                        accept="image/*,.pdf,.txt,.csv,.xlsx,.xls,.zip"
                        on:change={handleFileSelect}
                    />
                </label>
                <p class="supported-types">Files: PDF, Images, Excel, CSV, Text, ZIP</p>
                <p class="supported-types">Paste: Tables, Text snippets, Images</p>
            </div>
        {/if}
    </div>

    {#if error}
        <div class="error-message">{error}</div>
    {/if}

    <!-- Resources List -->
    <div class="resources-list-container">
        {#if loading}
            <div class="resources-loading">Loading resources...</div>
        {:else if resources.length > 0}
            <div class="resources-list">
                {#each resources as resource}
                    {@const meta = parseResourceDescription(resource.description)}
                    <div class="resource-card">
                        <div class="resource-card-header">
                            <span class="resource-icon">{getResourceIcon(resource.resource_type)}</span>
                            <div class="resource-title-area">
                                <span class="resource-name">{resource.name}</span>
                                <span class="resource-type-badge">{resource.resource_type}</span>
                            </div>
                            <span
                                class="resource-status-badge"
                                style="background-color: {getStatusColor(resource.status)}"
                            >
                                {resource.status}
                            </span>
                            {#if showDeleteButton || (articleId && showUnlinkButton)}
                                <button
                                    class="resource-remove"
                                    on:click={() => handleRemoveResource(resource)}
                                    title={articleId && showUnlinkButton ? "Remove from article" : "Delete resource"}
                                >
                                    ×
                                </button>
                            {/if}
                        </div>
                        <div class="resource-metadata">
                            {#if meta.desc}
                                <div class="meta-row">
                                    <span class="meta-label">Description:</span>
                                    <span class="meta-value">{meta.desc}</span>
                                </div>
                            {/if}
                            {#if meta.reference}
                                <div class="meta-row">
                                    <span class="meta-label">Reference:</span>
                                    <span class="meta-value">{meta.reference}</span>
                                </div>
                            {/if}
                            {#if meta.source}
                                <div class="meta-row">
                                    <span class="meta-label">Source:</span>
                                    <span class="meta-value">{meta.source}</span>
                                </div>
                            {/if}
                            {#if meta.weblink}
                                <div class="meta-row">
                                    <span class="meta-label">Link:</span>
                                    <a href={meta.weblink} target="_blank" rel="noopener" class="meta-link">{meta.weblink}</a>
                                </div>
                            {/if}
                            {#if !meta.desc && !meta.reference && !meta.source && !meta.weblink}
                                <div class="meta-row no-metadata">
                                    <span class="meta-value">No additional metadata</span>
                                </div>
                            {/if}
                        </div>
                    </div>
                {/each}
            </div>
        {:else}
            <p class="no-resources">No resources yet. Upload files or paste content above.</p>
        {/if}
    </div>
</div>

<!-- Resource Metadata Modal -->
{#if showMetadataModal && pendingResource}
    <div class="modal-overlay" on:click={closeMetadataModal} role="dialog" aria-modal="true">
        <div class="modal metadata-modal" on:click|stopPropagation>
            <div class="modal-header">
                <h3>Add Resource Metadata</h3>
                <button class="close-btn" on:click={closeMetadataModal}>×</button>
            </div>

            <div class="modal-body">
                <p class="modal-hint">
                    {#if pendingResource.type === 'file'}
                        File: {pendingResource.file?.name}
                    {:else if pendingResource.type === 'table'}
                        Table with {pendingResource.tableData?.data.length} rows
                    {:else}
                        Text snippet ({pendingResource.textContent?.length} characters)
                    {/if}
                </p>

                <div class="form-group">
                    <label for="meta-title">Title *</label>
                    <input
                        id="meta-title"
                        type="text"
                        bind:value={resourceMetadata.title}
                        placeholder="Resource title"
                        required
                    />
                </div>

                <div class="form-group">
                    <label for="meta-description">Description</label>
                    <textarea
                        id="meta-description"
                        bind:value={resourceMetadata.description}
                        placeholder="Brief description of this resource"
                        rows="2"
                    ></textarea>
                </div>

                <div class="form-group">
                    <label for="meta-reference">Reference</label>
                    <input
                        id="meta-reference"
                        type="text"
                        bind:value={resourceMetadata.reference}
                        placeholder="e.g., Report ID, Document Number"
                    />
                </div>

                <div class="form-group">
                    <label for="meta-source">Source</label>
                    <input
                        id="meta-source"
                        type="text"
                        bind:value={resourceMetadata.source}
                        placeholder="e.g., Bloomberg, Reuters, Internal"
                    />
                </div>

                <div class="form-group">
                    <label for="meta-weblink">Web Link</label>
                    <input
                        id="meta-weblink"
                        type="url"
                        bind:value={resourceMetadata.weblink}
                        placeholder="https://..."
                    />
                </div>
            </div>

            <div class="modal-footer">
                <button class="cancel-btn" on:click={closeMetadataModal} disabled={metadataSaving}>
                    Cancel
                </button>
                <button
                    class="save-btn"
                    on:click={saveResourceWithMetadata}
                    disabled={!resourceMetadata.title.trim() || metadataSaving}
                >
                    {metadataSaving ? 'Saving...' : 'Save Resource'}
                </button>
            </div>
        </div>
    </div>
{/if}

<style>
    .resource-editor {
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }

    .drop-zone {
        padding: 1.5rem;
        border: 2px dashed #d1d5db;
        border-radius: 8px;
        text-align: center;
        transition: all 0.2s;
        background: #fafafa;
    }

    .drop-zone.dragging {
        border-color: #3b82f6;
        background: #eff6ff;
    }

    .drop-zone-content {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 0.5rem;
    }

    .drop-icon {
        font-size: 2rem;
    }

    .drop-zone p {
        margin: 0;
        color: #6b7280;
        font-size: 0.875rem;
    }

    .drop-hint {
        font-size: 0.75rem !important;
        color: #9ca3af !important;
    }

    .file-select-btn {
        display: inline-block;
        padding: 0.5rem 1rem;
        background: #3b82f6;
        color: white;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.875rem;
        font-weight: 500;
        transition: background 0.2s;
    }

    .file-select-btn:hover {
        background: #2563eb;
    }

    .file-select-btn input {
        display: none;
    }

    .supported-types {
        font-size: 0.75rem !important;
        color: #9ca3af !important;
        margin-top: 0.5rem !important;
    }

    .upload-progress {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.75rem;
        color: #3b82f6;
        font-size: 0.875rem;
    }

    .spinner-small {
        width: 20px;
        height: 20px;
        border: 2px solid #e5e7eb;
        border-top: 2px solid #3b82f6;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    .error-message {
        padding: 0.75rem;
        background: #fee2e2;
        color: #dc2626;
        border-radius: 4px;
        font-size: 0.875rem;
    }

    .resources-list-container {
        flex: 1;
        overflow-y: auto;
    }

    .resources-loading,
    .no-resources {
        padding: 2rem;
        text-align: center;
        color: #6b7280;
        font-size: 0.875rem;
    }

    .resources-list {
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
    }

    .resource-card {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        overflow: hidden;
        transition: all 0.2s;
    }

    .resource-card:hover {
        border-color: #d1d5db;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    }

    .resource-card-header {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.75rem 1rem;
        background: #f9fafb;
        border-bottom: 1px solid #e5e7eb;
    }

    .resource-icon {
        font-size: 1.5rem;
        flex-shrink: 0;
    }

    .resource-title-area {
        flex: 1;
        min-width: 0;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .resource-name {
        font-size: 0.9rem;
        font-weight: 600;
        color: #1f2937;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .resource-type-badge {
        padding: 0.125rem 0.5rem;
        background: #e5e7eb;
        color: #4b5563;
        border-radius: 9999px;
        font-size: 0.7rem;
        text-transform: uppercase;
        font-weight: 500;
        flex-shrink: 0;
    }

    .resource-status-badge {
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        font-size: 0.7rem;
        font-weight: 500;
        color: white;
        text-transform: capitalize;
        flex-shrink: 0;
    }

    .resource-remove {
        width: 28px;
        height: 28px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: none;
        border: none;
        color: #9ca3af;
        font-size: 1.25rem;
        cursor: pointer;
        border-radius: 4px;
        flex-shrink: 0;
        transition: all 0.2s;
    }

    .resource-remove:hover {
        background: #fee2e2;
        color: #dc2626;
    }

    .resource-metadata {
        padding: 0.75rem 1rem;
    }

    .meta-row {
        display: flex;
        gap: 0.5rem;
        font-size: 0.8rem;
        padding: 0.25rem 0;
    }

    .meta-row.no-metadata {
        color: #9ca3af;
        font-style: italic;
    }

    .meta-label {
        color: #6b7280;
        font-weight: 500;
        min-width: 80px;
        flex-shrink: 0;
    }

    .meta-value {
        color: #374151;
        word-break: break-word;
    }

    .meta-link {
        color: #3b82f6;
        text-decoration: none;
        word-break: break-all;
    }

    .meta-link:hover {
        text-decoration: underline;
    }

    /* Modal Styles */
    .modal-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.5);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 1000;
        padding: 2rem;
    }

    .modal {
        background: white;
        border-radius: 8px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        max-width: 500px;
        width: 100%;
        max-height: 90vh;
        overflow-y: auto;
    }

    .modal-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1rem 1.5rem;
        border-bottom: 1px solid #e5e7eb;
    }

    .modal-header h3 {
        margin: 0;
        font-size: 1.1rem;
        color: #1f2937;
    }

    .close-btn {
        background: none;
        border: none;
        font-size: 1.5rem;
        color: #6b7280;
        cursor: pointer;
        padding: 0;
        line-height: 1;
    }

    .close-btn:hover {
        color: #1f2937;
    }

    .modal-body {
        padding: 1.5rem;
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }

    .modal-hint {
        margin: 0;
        padding: 0.75rem;
        background: #f3f4f6;
        border-radius: 6px;
        font-size: 0.85rem;
        color: #4b5563;
    }

    .form-group {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
    }

    .form-group label {
        font-weight: 600;
        color: #333;
        font-size: 0.875rem;
    }

    .form-group input,
    .form-group textarea {
        padding: 0.75rem;
        border: 1px solid #e0e0e0;
        border-radius: 4px;
        font-size: 0.9rem;
        font-family: inherit;
    }

    .form-group textarea {
        resize: vertical;
        min-height: 60px;
    }

    .form-group input:focus,
    .form-group textarea:focus {
        outline: none;
        border-color: #3b82f6;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
    }

    .modal-footer {
        display: flex;
        justify-content: flex-end;
        gap: 0.75rem;
        padding: 1rem 1.5rem;
        border-top: 1px solid #e5e7eb;
        background: #f9fafb;
    }

    .cancel-btn {
        padding: 0.625rem 1.25rem;
        background: white;
        color: #374151;
        border: 1px solid #d1d5db;
        border-radius: 6px;
        cursor: pointer;
        font-weight: 500;
        font-size: 0.875rem;
        transition: all 0.2s;
    }

    .cancel-btn:hover:not(:disabled) {
        background: #f9fafb;
        border-color: #9ca3af;
    }

    .save-btn {
        padding: 0.625rem 1.25rem;
        background: #3b82f6;
        color: white;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        font-weight: 500;
        font-size: 0.875rem;
        transition: all 0.2s;
    }

    .save-btn:hover:not(:disabled) {
        background: #2563eb;
    }

    .save-btn:disabled,
    .cancel-btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }
</style>
