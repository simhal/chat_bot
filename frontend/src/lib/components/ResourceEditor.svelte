<script lang="ts">
    import { createEventDispatcher } from 'svelte';
    import { uploadFileResource, createTextResource, createTableResource, linkResourceToArticle, unlinkResourceFromArticle, deleteResource, updateResource, getResourceContentUrl, getResource, updateTextContent, updateTableContent, updateTimeseriesData, publishTableResource, recallTableResource, type Resource, type ResourceDetail } from '$lib/api';

    // Props
    export let resources: Resource[] = [];  // All resources linked to article
    export let topicResources: Resource[] = [];  // All topic-level resources (for categorization)
    export let globalResources: Resource[] = [];  // All global resources (for categorization)
    export let articleId: number | undefined = undefined;
    export let groupId: number | undefined = undefined;
    export let groupName: string | undefined = undefined;
    export let loading: boolean = false;
    export let showDeleteButton: boolean = true;
    export let showUnlinkButton: boolean = true;
    export let allowUpload: boolean = true;  // Allow uploading new resources

    // Categorize linked resources by their origin
    $: globalResourceIds = new Set(globalResources.map(r => r.id));
    $: topicResourceIds = new Set(topicResources.map(r => r.id));

    // Split linked resources into categories
    $: linkedGlobalResources = resources.filter(r => globalResourceIds.has(r.id));
    $: linkedTopicResources = resources.filter(r => topicResourceIds.has(r.id));
    $: articleSpecificResources = resources.filter(r => !globalResourceIds.has(r.id) && !topicResourceIds.has(r.id));

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

    let uploadProgress = '';
    let error = '';

    // Preview popup state
    let previewResource: Resource | null = null;
    let previewTableData: { columns: string[]; data: any[][] } | null = null;
    let previewHtmlChildHashId: string | null = null;  // For published tables with HTML child
    let previewLoading = false;
    let sortColumn: number | null = null;
    let sortDirection: 'asc' | 'desc' = 'asc';

    // Edit popup state
    let editingResource: Resource | null = null;
    let editMetadata = {
        title: '',
        description: '',
        reference: '',
        weblink: '',
        source: ''
    };
    let editSaving = false;

    // Content editing state
    let contentEditResource: ResourceDetail | null = null;
    let contentEditValue: string = '';
    let contentEditTableData: { columns: string[]; data: any[][] } | null = null;
    let contentEditTimeseriesData: Array<{ timestamp: string; values: Record<string, any> }> | null = null;
    let contentEditLoading = false;
    let contentEditSaving = false;

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

    // Import modal state
    let showImportModal = false;
    let importSource: 'global' | 'topic' = 'global';
    let importSearch = '';
    let attachingResourceId: number | null = null;

    // Section collapse state
    let articleSectionOpen = true;
    let topicSectionOpen = true;
    let globalSectionOpen = true;

    // File input reference
    let fileInput: HTMLInputElement;

    // Filtered resources for import modal
    $: availableGlobalResources = globalResources.filter(r => !isResourceLinked(r));
    $: availableTopicResources = topicResources.filter(r => !isResourceLinked(r));
    $: filteredImportResources = (importSource === 'global' ? availableGlobalResources : availableTopicResources)
        .filter(r => !importSearch || r.name.toLowerCase().includes(importSearch.toLowerCase()));

    // Handle file select from button
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

    // Paste handler for clipboard content - works anywhere in the component
    async function handlePaste(e: ClipboardEvent) {
        if (!allowUpload) return;

        // Don't intercept paste if user is in an input field
        const target = e.target as HTMLElement;
        if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return;

        e.preventDefault();

        const clipboardData = e.clipboardData;
        if (!clipboardData) return;

        // Check for HTML content FIRST (Excel tables, rich text)
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

        // Check for plain text that looks like TSV
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

        // Check for files (images, etc.)
        if (clipboardData.files && clipboardData.files.length > 0) {
            const file = clipboardData.files[0];
            openMetadataModal({
                type: 'file',
                file: file,
                suggestedName: `Pasted ${file.type.split('/')[0]} ${new Date().toLocaleString()}`
            });
            return;
        }

        // Fall back to plain text
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
                    groupName
                );
                if (articleId && groupId) {
                    await linkResourceToArticle(resource.id, articleId);
                }
            } else if (pendingResource.type === 'table' && pendingResource.tableData) {
                resource = await createTableResource(
                    resourceMetadata.title,
                    pendingResource.tableData,
                    groupId,
                    fullDescription,
                    undefined,
                    groupName
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
                    groupName
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

    // Helper functions for parsing
    function containsTable(html: string): boolean {
        return /<table[\s>]/i.test(html);
    }

    function looksLikeTsvData(text: string): boolean {
        const lines = text.trim().split('\n');
        if (lines.length < 2) return false;
        const linesWithTabs = lines.filter(line => line.includes('\t'));
        return linesWithTabs.length > lines.length * 0.5;
    }

    function parseHtmlTable(html: string): { columns: string[]; data: any[][] } | null {
        try {
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const table = doc.querySelector('table');

            if (!table) return null;

            const rows = Array.from(table.querySelectorAll('tr'));
            if (rows.length === 0) return null;

            const headerRow = rows[0];
            const columns = Array.from(headerRow.querySelectorAll('th, td')).map(cell =>
                cell.textContent?.trim() || ''
            );

            const data: any[][] = [];
            for (let i = 1; i < rows.length; i++) {
                const cells = Array.from(rows[i].querySelectorAll('td, th'));
                const rowData = cells.map(cell => {
                    const text = cell.textContent?.trim() || '';
                    const num = parseFloat(text.replace(/[,\s]/g, ''));
                    return !isNaN(num) && text !== '' ? num : text;
                });
                if (rowData.some(v => v !== '')) {
                    data.push(rowData);
                }
            }

            // Replace empty column headers with placeholder names
            const finalColumns = columns.map((col, i) =>
                col === '' ? `Column ${i + 1}` : col
            );

            return { columns: finalColumns, data };
        } catch (e) {
            console.error('Failed to parse HTML table:', e);
            return null;
        }
    }

    function parseTsv(text: string): { columns: string[]; data: any[][] } | null {
        try {
            const lines = text.trim().split('\n');
            if (lines.length < 2) return null;

            const rawColumns = lines[0].split('\t').map(c => c.trim());
            // Replace empty column headers with placeholder names
            const columns = rawColumns.map((col, i) =>
                col === '' ? `Column ${i + 1}` : col
            );

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
                await unlinkResourceFromArticle(resource.id, articleId);
            } else {
                await deleteResource(resource.id);
            }
            dispatch('refresh');
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to remove resource';
            dispatch('error', error);
        }
    }

    // Publish a table resource (creates HTML/IMAGE children)
    async function handlePublishTable(resource: Resource) {
        if (resource.resource_type !== 'table') return;
        if (!confirm(`Publish "${resource.name}"? This will create permanent HTML and image versions.`)) return;

        try {
            error = '';
            await publishTableResource(resource.id);
            dispatch('refresh');
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to publish table resource';
            dispatch('error', error);
        }
    }

    // Recall a published table resource (deletes children, returns to draft)
    async function handleRecallTable(resource: Resource) {
        if (resource.resource_type !== 'table') return;
        if (!confirm(`Recall "${resource.name}"? This will delete the published HTML and image versions.`)) return;

        try {
            error = '';
            await recallTableResource(resource.id);
            dispatch('refresh');
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to recall table resource';
            dispatch('error', error);
        }
    }

    // Attach a global or topic resource to the article
    async function handleAttachResource(resource: Resource) {
        if (!articleId) return;

        try {
            attachingResourceId = resource.id;
            error = '';
            await linkResourceToArticle(resource.id, articleId);
            dispatch('refresh');
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to attach resource';
            dispatch('error', error);
        } finally {
            attachingResourceId = null;
        }
    }

    // Check if resource is already linked to article
    function isResourceLinked(resource: Resource): boolean {
        return resources.some(r => r.id === resource.id);
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
            'timeseries': '📈',
            'article': '📰'
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

    function isImageResource(resourceType: string): boolean {
        return resourceType === 'image';
    }

    function isViewableResource(resourceType: string): boolean {
        return ['image', 'pdf', 'text', 'html', 'table', 'article'].includes(resourceType);
    }

    function isEditableContent(resourceType: string): boolean {
        return ['text', 'table', 'timeseries'].includes(resourceType);
    }

    function handleImageDragStart(e: DragEvent, resource: Resource) {
        if (!e.dataTransfer) return;
        const imageUrl = getResourceContentUrl(resource.hash_id);
        const markdownImage = `![${resource.name}](${imageUrl})`;
        e.dataTransfer.setData('text/plain', markdownImage);
        e.dataTransfer.effectAllowed = 'copy';
    }

    function handleResourceDragStart(e: DragEvent, resource: Resource) {
        if (!e.dataTransfer) return;
        const resourceLink = `[${resource.name}](resource:${resource.hash_id})`;
        e.dataTransfer.setData('text/plain', resourceLink);
        e.dataTransfer.effectAllowed = 'copy';
    }

    function handleTableDragStart(e: DragEvent, resource: Resource) {
        if (!e.dataTransfer) return;
        e.dataTransfer.effectAllowed = 'copy';
        // Set custom type to indicate this is a table that should be embedded as markdown
        e.dataTransfer.setData('application/x-table-resource', JSON.stringify({
            hashId: resource.hash_id,
            name: resource.name
        }));
        // Fallback for text/plain (used if custom type not handled)
        e.dataTransfer.setData('text/plain', `[${resource.name}](resource:${resource.hash_id})`);
    }

    function handleDragStart(e: DragEvent, resource: Resource) {
        if (isImageResource(resource.resource_type)) {
            handleImageDragStart(e, resource);
        } else if (resource.resource_type === 'table') {
            handleTableDragStart(e, resource);
        } else {
            handleResourceDragStart(e, resource);
        }
    }

    async function handleViewResource(resource: Resource) {
        previewResource = resource;
        previewTableData = null;
        previewHtmlChildHashId = null;
        sortColumn = null;
        sortDirection = 'asc';

        // Fetch table data for table resources
        if (resource.resource_type === 'table') {
            try {
                previewLoading = true;
                const detail = await getResource(resource.id);

                // For published tables, check if there's an HTML child to display
                if (resource.status === 'published' && detail.children && detail.children.length > 0) {
                    const htmlChild = detail.children.find(c => c.resource_type === 'html');
                    if (htmlChild) {
                        previewHtmlChildHashId = htmlChild.hash_id;
                        previewLoading = false;
                        return;  // Use HTML child instead of raw table data
                    }
                }

                // Fall back to raw table data
                if (detail.table_data?.data) {
                    previewTableData = {
                        columns: detail.table_data.data.columns || [],
                        data: detail.table_data.data.data || []
                    };
                }
            } catch (e) {
                error = e instanceof Error ? e.message : 'Failed to load table data';
            } finally {
                previewLoading = false;
            }
        }
    }

    function closePreviewModal() {
        previewResource = null;
        previewTableData = null;
        previewHtmlChildHashId = null;
        sortColumn = null;
        sortDirection = 'asc';
    }

    function handleSort(colIndex: number) {
        if (sortColumn === colIndex) {
            sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            sortColumn = colIndex;
            sortDirection = 'asc';
        }
    }

    $: sortedTableData = previewTableData ? {
        columns: previewTableData.columns,
        data: sortColumn !== null
            ? [...previewTableData.data].sort((a, b) => {
                const aVal = a[sortColumn!];
                const bVal = b[sortColumn!];
                const aNum = typeof aVal === 'number' ? aVal : parseFloat(String(aVal).replace(/[,\s]/g, ''));
                const bNum = typeof bVal === 'number' ? bVal : parseFloat(String(bVal).replace(/[,\s]/g, ''));

                if (!isNaN(aNum) && !isNaN(bNum)) {
                    return sortDirection === 'asc' ? aNum - bNum : bNum - aNum;
                }
                const aStr = String(aVal || '').toLowerCase();
                const bStr = String(bVal || '').toLowerCase();
                if (sortDirection === 'asc') {
                    return aStr.localeCompare(bStr);
                }
                return bStr.localeCompare(aStr);
            })
            : previewTableData.data
    } : null;

    function handleEditResource(resource: Resource) {
        editingResource = resource;
        const meta = parseResourceDescription(resource.description);
        editMetadata = {
            title: resource.name,
            description: meta.desc,
            reference: meta.reference,
            weblink: meta.weblink,
            source: meta.source
        };
    }

    function closeEditModal() {
        editingResource = null;
        editMetadata = { title: '', description: '', reference: '', weblink: '', source: '' };
        editSaving = false;
    }

    async function saveEditedResource() {
        if (!editingResource || !editMetadata.title.trim()) return;

        try {
            editSaving = true;
            error = '';

            const descriptionParts = [];
            if (editMetadata.description) descriptionParts.push(editMetadata.description);
            if (editMetadata.reference) descriptionParts.push(`Reference: ${editMetadata.reference}`);
            if (editMetadata.weblink) descriptionParts.push(`Link: ${editMetadata.weblink}`);
            if (editMetadata.source) descriptionParts.push(`Source: ${editMetadata.source}`);
            const fullDescription = descriptionParts.join(' | ');

            await updateResource(editingResource.id, editMetadata.title, fullDescription);
            closeEditModal();
            dispatch('refresh');
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to update resource';
            dispatch('error', error);
        } finally {
            editSaving = false;
        }
    }

    // Content editing functions
    async function handleEditContent(resource: Resource) {
        try {
            contentEditLoading = true;
            error = '';

            // Fetch full resource details including content
            const detail = await getResource(resource.id);
            contentEditResource = detail;

            if (detail.resource_type === 'text' && detail.text_data) {
                contentEditValue = detail.text_data.content || '';
            } else if (detail.resource_type === 'table' && detail.table_data?.data) {
                contentEditTableData = {
                    columns: detail.table_data.data.columns || [],
                    data: detail.table_data.data.data || []
                };
            } else if (detail.resource_type === 'timeseries' && detail.timeseries_data) {
                // Fetch timeseries data from the content endpoint
                const response = await fetch(getResourceContentUrl(resource.hash_id));
                if (response.ok) {
                    const tsData = await response.json();
                    contentEditTimeseriesData = tsData.data || [];
                }
            }
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to load resource content';
            dispatch('error', error);
            contentEditResource = null;
        } finally {
            contentEditLoading = false;
        }
    }

    function closeContentEditModal() {
        contentEditResource = null;
        contentEditValue = '';
        contentEditTableData = null;
        contentEditTimeseriesData = null;
        contentEditSaving = false;
    }

    async function saveEditedContent() {
        if (!contentEditResource) return;

        try {
            contentEditSaving = true;
            error = '';

            if (contentEditResource.resource_type === 'text') {
                await updateTextContent(contentEditResource.id, contentEditValue);
            } else if (contentEditResource.resource_type === 'table' && contentEditTableData) {
                await updateTableContent(contentEditResource.id, contentEditTableData);
            } else if (contentEditResource.resource_type === 'timeseries' && contentEditTimeseriesData) {
                await updateTimeseriesData(contentEditResource.id, contentEditTimeseriesData);
            }

            closeContentEditModal();
            dispatch('refresh');
        } catch (e) {
            error = e instanceof Error ? e.message : 'Failed to save content';
            dispatch('error', error);
        } finally {
            contentEditSaving = false;
        }
    }

    // Table editing helpers
    function updateTableCell(rowIndex: number, colIndex: number, value: string) {
        if (!contentEditTableData) return;
        const numVal = parseFloat(value.replace(/[,\s]/g, ''));
        const newValue = !isNaN(numVal) && value !== '' ? numVal : value;
        const newData = contentEditTableData.data.map((row, ri) =>
            ri === rowIndex ? row.map((cell, ci) => ci === colIndex ? newValue : cell) : row
        );
        contentEditTableData = { ...contentEditTableData, data: newData };
    }

    function updateTableHeader(colIndex: number, value: string) {
        if (!contentEditTableData) return;
        const newColumns = contentEditTableData.columns.map((col, i) => i === colIndex ? value : col);
        contentEditTableData = { ...contentEditTableData, columns: newColumns };
    }

    function addTableRow() {
        if (!contentEditTableData) return;
        const newRow = contentEditTableData.columns.map(() => '');
        contentEditTableData = {
            ...contentEditTableData,
            data: [...contentEditTableData.data, newRow]
        };
    }

    function removeTableRow(rowIndex: number) {
        if (!contentEditTableData) return;
        contentEditTableData = {
            ...contentEditTableData,
            data: contentEditTableData.data.filter((_, i) => i !== rowIndex)
        };
    }

    function addTableColumn() {
        if (!contentEditTableData) return;
        contentEditTableData = {
            columns: [...contentEditTableData.columns, `Column ${contentEditTableData.columns.length + 1}`],
            data: contentEditTableData.data.map(row => [...row, ''])
        };
    }

    function removeTableColumn(colIndex: number) {
        if (!contentEditTableData) return;
        contentEditTableData = {
            columns: contentEditTableData.columns.filter((_, i) => i !== colIndex),
            data: contentEditTableData.data.map(row => row.filter((_, i) => i !== colIndex))
        };
    }

    // Timeseries editing helpers
    function updateTimeseriesRow(rowIndex: number, field: string, value: string) {
        if (!contentEditTimeseriesData) return;
        if (field === 'timestamp') {
            contentEditTimeseriesData[rowIndex].timestamp = value;
        } else {
            const numVal = parseFloat(value.replace(/[,\s]/g, ''));
            contentEditTimeseriesData[rowIndex].values[field] = !isNaN(numVal) && value !== '' ? numVal : value;
        }
        contentEditTimeseriesData = contentEditTimeseriesData; // Trigger reactivity
    }

    function addTimeseriesRow() {
        if (!contentEditTimeseriesData || contentEditTimeseriesData.length === 0) return;
        const valueKeys = Object.keys(contentEditTimeseriesData[0].values);
        const newValues: Record<string, any> = {};
        valueKeys.forEach(key => newValues[key] = 0);
        contentEditTimeseriesData = [...contentEditTimeseriesData, { timestamp: new Date().toISOString(), values: newValues }];
    }

    function removeTimeseriesRow(rowIndex: number) {
        if (!contentEditTimeseriesData) return;
        contentEditTimeseriesData = contentEditTimeseriesData.filter((_, i) => i !== rowIndex);
    }

    // Open import modal
    function openImportModal(source: 'global' | 'topic') {
        importSource = source;
        importSearch = '';
        showImportModal = true;
    }

    function closeImportModal() {
        showImportModal = false;
        importSearch = '';
    }
</script>

<div
    class="resource-editor"
    on:paste={handlePaste}
    role="region"
    tabindex="0"
>
    <!-- Upload Controls at Top -->
    {#if allowUpload}
        <div class="upload-controls">
            <label class="upload-btn">
                📁 Upload File
                <input
                    bind:this={fileInput}
                    type="file"
                    accept="image/*,.pdf,.txt,.csv,.xlsx,.xls,.zip"
                    on:change={handleFileSelect}
                />
            </label>
            <span class="paste-hint">Paste images, tables, or text (Ctrl+V)</span>
        </div>
    {/if}

    {#if error}
        <div class="error-message">{error}</div>
    {/if}

    {#if uploadProgress}
        <div class="upload-progress">
            <div class="spinner-small"></div>
            <span>{uploadProgress}</span>
        </div>
    {/if}

    <!-- Three Resource Sections -->
    <div class="resources-sections">
        <!-- Article Resources Section -->
        <div class="resource-section">
            <button class="section-header" on:click={() => articleSectionOpen = !articleSectionOpen}>
                <span class="toggle-icon">{articleSectionOpen ? '▼' : '▶'}</span>
                <span class="section-title">Article Resources</span>
                <span class="section-count">{articleSpecificResources.length}</span>
            </button>
            {#if articleSectionOpen}
                <div class="section-content">
                    {#if loading}
                        <div class="resources-loading">Loading...</div>
                    {:else if articleSpecificResources.length > 0}
                        <div class="resources-list">
                            {#each articleSpecificResources as resource}
                                <div
                                    class="resource-item draggable-resource"
                                    draggable={true}
                                    on:dragstart={(e) => handleDragStart(e, resource)}
                                >
                                    <span class="resource-icon">{getResourceIcon(resource.resource_type)}</span>
                                    <span class="resource-name">{resource.name}</span>
                                    <span class="resource-type-badge">{resource.resource_type}</span>
                                    <div class="resource-actions">
                                        {#if isViewableResource(resource.resource_type)}
                                            <button class="action-btn" on:click={() => handleViewResource(resource)} title="View">👁</button>
                                        {/if}
                                        {#if isEditableContent(resource.resource_type)}
                                            <button class="action-btn" on:click={() => handleEditContent(resource)} title="Edit Content">📝</button>
                                        {/if}
                                        <button class="action-btn" on:click={() => handleEditResource(resource)} title="Edit Metadata">✎</button>
                                        {#if resource.resource_type === 'table' && resource.status !== 'published'}
                                            <button class="action-btn publish" on:click={() => handlePublishTable(resource)} title="Publish">📤</button>
                                        {/if}
                                        {#if resource.resource_type === 'table' && resource.status === 'published'}
                                            <button class="action-btn recall" on:click={() => handleRecallTable(resource)} title="Recall">📥</button>
                                        {/if}
                                        {#if showDeleteButton || (articleId && showUnlinkButton)}
                                            <button class="action-btn remove" on:click={() => handleRemoveResource(resource)} title="Remove">×</button>
                                        {/if}
                                    </div>
                                </div>
                            {/each}
                        </div>
                    {:else}
                        <p class="no-resources">No article resources</p>
                    {/if}
                </div>
            {/if}
        </div>

        <!-- Topic Resources Section -->
        {#if articleId}
            <div class="resource-section">
                <div class="section-header-row">
                    <button class="section-header" on:click={() => topicSectionOpen = !topicSectionOpen}>
                        <span class="toggle-icon">{topicSectionOpen ? '▼' : '▶'}</span>
                        <span class="section-title">Topic Resources</span>
                        <span class="section-count">{linkedTopicResources.length}{#if availableTopicResources.length > 0}<span class="available-count">+{availableTopicResources.length}</span>{/if}</span>
                    </button>
                    {#if availableTopicResources.length > 0}
                        <button class="import-btn" on:click={() => openImportModal('topic')}>
                            + Import ({availableTopicResources.length})
                        </button>
                    {/if}
                </div>
                {#if topicSectionOpen}
                    <div class="section-content">
                        {#if linkedTopicResources.length > 0}
                            <div class="resources-list">
                                {#each linkedTopicResources as resource}
                                    <div
                                        class="resource-item draggable-resource"
                                        draggable={true}
                                        on:dragstart={(e) => handleDragStart(e, resource)}
                                    >
                                        <span class="resource-icon">{getResourceIcon(resource.resource_type)}</span>
                                        <span class="resource-name">{resource.name}</span>
                                        <span class="resource-type-badge">{resource.resource_type}</span>
                                        <div class="resource-actions">
                                            {#if isViewableResource(resource.resource_type)}
                                                <button class="action-btn" on:click={() => handleViewResource(resource)} title="View">👁</button>
                                            {/if}
                                            {#if isEditableContent(resource.resource_type)}
                                                <button class="action-btn" on:click={() => handleEditContent(resource)} title="Edit Content">📝</button>
                                            {/if}
                                            <button class="action-btn" on:click={() => handleEditResource(resource)} title="Edit Metadata">✎</button>
                                            {#if resource.resource_type === 'table' && resource.status !== 'published'}
                                                <button class="action-btn publish" on:click={() => handlePublishTable(resource)} title="Publish">📤</button>
                                            {/if}
                                            {#if resource.resource_type === 'table' && resource.status === 'published'}
                                                <button class="action-btn recall" on:click={() => handleRecallTable(resource)} title="Recall">📥</button>
                                            {/if}
                                            {#if articleId && showUnlinkButton}
                                                <button class="action-btn remove" on:click={() => handleRemoveResource(resource)} title="Remove">×</button>
                                            {/if}
                                        </div>
                                    </div>
                                {/each}
                            </div>
                        {:else}
                            <p class="no-resources">{topicResources.length === 0 ? 'No topic resources available' : 'No topic resources attached'}</p>
                        {/if}
                    </div>
                {/if}
            </div>

            <!-- Global Resources Section -->
            <div class="resource-section">
                <div class="section-header-row">
                    <button class="section-header" on:click={() => globalSectionOpen = !globalSectionOpen}>
                        <span class="toggle-icon">{globalSectionOpen ? '▼' : '▶'}</span>
                        <span class="section-title">Global Resources</span>
                        <span class="section-count">{linkedGlobalResources.length}{#if availableGlobalResources.length > 0}<span class="available-count">+{availableGlobalResources.length}</span>{/if}</span>
                    </button>
                    {#if availableGlobalResources.length > 0}
                        <button class="import-btn" on:click={() => openImportModal('global')}>
                            + Import ({availableGlobalResources.length})
                        </button>
                    {/if}
                </div>
                {#if globalSectionOpen}
                    <div class="section-content">
                        {#if linkedGlobalResources.length > 0}
                            <div class="resources-list">
                                {#each linkedGlobalResources as resource}
                                    <div
                                        class="resource-item draggable-resource"
                                        draggable={true}
                                        on:dragstart={(e) => handleDragStart(e, resource)}
                                    >
                                        <span class="resource-icon">{getResourceIcon(resource.resource_type)}</span>
                                        <span class="resource-name">{resource.name}</span>
                                        <span class="resource-type-badge">{resource.resource_type}</span>
                                        <div class="resource-actions">
                                            {#if isViewableResource(resource.resource_type)}
                                                <button class="action-btn" on:click={() => handleViewResource(resource)} title="View">👁</button>
                                            {/if}
                                            {#if isEditableContent(resource.resource_type)}
                                                <button class="action-btn" on:click={() => handleEditContent(resource)} title="Edit Content">📝</button>
                                            {/if}
                                            <button class="action-btn" on:click={() => handleEditResource(resource)} title="Edit Metadata">✎</button>
                                            {#if resource.resource_type === 'table' && resource.status !== 'published'}
                                                <button class="action-btn publish" on:click={() => handlePublishTable(resource)} title="Publish">📤</button>
                                            {/if}
                                            {#if resource.resource_type === 'table' && resource.status === 'published'}
                                                <button class="action-btn recall" on:click={() => handleRecallTable(resource)} title="Recall">📥</button>
                                            {/if}
                                            {#if articleId && showUnlinkButton}
                                                <button class="action-btn remove" on:click={() => handleRemoveResource(resource)} title="Remove">×</button>
                                            {/if}
                                        </div>
                                    </div>
                                {/each}
                            </div>
                        {:else}
                            <p class="no-resources">{globalResources.length === 0 ? 'No global resources available' : 'No global resources attached'}</p>
                        {/if}
                    </div>
                {/if}
            </div>
        {/if}
    </div>
</div>

<!-- Import Resources Modal -->
{#if showImportModal}
    <div class="modal-overlay" on:click={closeImportModal} role="dialog" aria-modal="true">
        <div class="modal import-modal" on:click|stopPropagation>
            <div class="modal-header">
                <h3>{importSource === 'global' ? 'Import Global Resource' : 'Import Topic Resource'}</h3>
                <button class="close-btn" on:click={closeImportModal}>×</button>
            </div>

            <div class="modal-body">
                <div class="import-search">
                    <input
                        type="text"
                        placeholder="Search resources..."
                        bind:value={importSearch}
                    />
                </div>

                <div class="import-tabs">
                    <button
                        class="import-tab"
                        class:active={importSource === 'global'}
                        on:click={() => importSource = 'global'}
                        disabled={availableGlobalResources.length === 0}
                    >
                        Global ({availableGlobalResources.length})
                    </button>
                    <button
                        class="import-tab"
                        class:active={importSource === 'topic'}
                        on:click={() => importSource = 'topic'}
                        disabled={availableTopicResources.length === 0}
                    >
                        Topic ({availableTopicResources.length})
                    </button>
                </div>

                <div class="import-list">
                    {#if filteredImportResources.length === 0}
                        <p class="no-resources">No resources available to import.</p>
                    {:else}
                        {#each filteredImportResources as resource}
                            {@const meta = parseResourceDescription(resource.description)}
                            <div class="import-item">
                                <div class="import-item-info">
                                    <span class="resource-icon">{getResourceIcon(resource.resource_type)}</span>
                                    <div class="import-item-details">
                                        <span class="resource-name">{resource.name}</span>
                                        <span class="resource-type-badge">{resource.resource_type}</span>
                                        {#if meta.desc}
                                            <span class="import-item-desc">{meta.desc}</span>
                                        {/if}
                                    </div>
                                </div>
                                <div class="import-item-actions">
                                    {#if isViewableResource(resource.resource_type)}
                                        <button
                                            class="resource-view"
                                            on:click={() => handleViewResource(resource)}
                                        >
                                            View
                                        </button>
                                    {/if}
                                    <button
                                        class="resource-attach"
                                        on:click={() => handleAttachResource(resource)}
                                        disabled={attachingResourceId === resource.id}
                                    >
                                        {attachingResourceId === resource.id ? 'Attaching...' : 'Attach'}
                                    </button>
                                </div>
                            </div>
                        {/each}
                    {/if}
                </div>
            </div>

            <div class="modal-footer">
                <button class="cancel-btn" on:click={closeImportModal}>Close</button>
            </div>
        </div>
    </div>
{/if}

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

<!-- Resource Preview Modal -->
{#if previewResource}
    <div class="modal-overlay preview-overlay" on:click={closePreviewModal} role="dialog" aria-modal="true">
        <div class="modal preview-modal" on:click|stopPropagation>
            <div class="modal-header">
                <h3>{previewResource.name}</h3>
                <div class="preview-actions">
                    <a
                        href={getResourceContentUrl(previewResource.hash_id)}
                        target="_blank"
                        rel="noopener"
                        class="open-external-btn"
                        title="Open in new tab"
                    >
                        ↗
                    </a>
                    <button class="close-btn" on:click={closePreviewModal}>×</button>
                </div>
            </div>
            <div class="preview-content">
                {#if previewResource.resource_type === 'image'}
                    <img
                        src={getResourceContentUrl(previewResource.hash_id)}
                        alt={previewResource.name}
                        class="preview-image"
                    />
                {:else if previewResource.resource_type === 'pdf'}
                    <iframe
                        src={getResourceContentUrl(previewResource.hash_id)}
                        title={previewResource.name}
                        class="preview-pdf"
                    ></iframe>
                {:else if previewResource.resource_type === 'text'}
                    <iframe
                        src={getResourceContentUrl(previewResource.hash_id)}
                        title={previewResource.name}
                        class="preview-text"
                    ></iframe>
                {:else if previewResource.resource_type === 'table'}
                    {#if previewLoading}
                        <div class="table-loading">
                            <div class="spinner-small"></div>
                            <span>Loading table...</span>
                        </div>
                    {:else if previewHtmlChildHashId}
                        <!-- Published table: show HTML child resource -->
                        <iframe
                            src={getResourceContentUrl(previewHtmlChildHashId)}
                            title={previewResource.name}
                            class="preview-table-html"
                        ></iframe>
                    {:else if sortedTableData}
                        <div class="preview-table-container">
                            <table class="preview-data-table">
                                <thead>
                                    <tr>
                                        {#each sortedTableData.columns as col, colIndex}
                                            <th
                                                class="sortable-header"
                                                on:click={() => handleSort(colIndex)}
                                            >
                                                <span class="header-text">{col}</span>
                                                <span class="sort-indicator">
                                                    {#if sortColumn === colIndex}
                                                        {sortDirection === 'asc' ? '▲' : '▼'}
                                                    {:else}
                                                        <span class="sort-inactive">⇅</span>
                                                    {/if}
                                                </span>
                                            </th>
                                        {/each}
                                    </tr>
                                </thead>
                                <tbody>
                                    {#each sortedTableData.data as row}
                                        <tr>
                                            {#each row as cell}
                                                <td>{cell}</td>
                                            {/each}
                                        </tr>
                                    {/each}
                                </tbody>
                            </table>
                        </div>
                    {:else}
                        <div class="preview-unsupported">
                            <p>Failed to load table data.</p>
                        </div>
                    {/if}
                {:else if previewResource.resource_type === 'article'}
                    <iframe
                        src={getResourceContentUrl(previewResource.hash_id)}
                        title={previewResource.name}
                        class="preview-article"
                    ></iframe>
                {:else}
                    <div class="preview-unsupported">
                        <p>Preview not available for this resource type.</p>
                        <a
                            href={getResourceContentUrl(previewResource.hash_id)}
                            target="_blank"
                            rel="noopener"
                            class="download-link"
                        >
                            Open in new tab
                        </a>
                    </div>
                {/if}
            </div>
        </div>
    </div>
{/if}

<!-- Edit Resource Modal -->
{#if editingResource}
    <div class="modal-overlay" on:click={closeEditModal} role="dialog" aria-modal="true">
        <div class="modal metadata-modal" on:click|stopPropagation>
            <div class="modal-header">
                <h3>Edit Resource</h3>
                <button class="close-btn" on:click={closeEditModal}>×</button>
            </div>

            <div class="modal-body">
                <p class="modal-hint">
                    Type: {editingResource.resource_type} | ID: {editingResource.hash_id}
                </p>

                <div class="form-group">
                    <label for="edit-title">Title *</label>
                    <input
                        id="edit-title"
                        type="text"
                        bind:value={editMetadata.title}
                        placeholder="Resource title"
                        required
                    />
                </div>

                <div class="form-group">
                    <label for="edit-description">Description</label>
                    <textarea
                        id="edit-description"
                        bind:value={editMetadata.description}
                        placeholder="Brief description of this resource"
                        rows="2"
                    ></textarea>
                </div>

                <div class="form-group">
                    <label for="edit-reference">Reference</label>
                    <input
                        id="edit-reference"
                        type="text"
                        bind:value={editMetadata.reference}
                        placeholder="e.g., Report ID, Document Number"
                    />
                </div>

                <div class="form-group">
                    <label for="edit-source">Source</label>
                    <input
                        id="edit-source"
                        type="text"
                        bind:value={editMetadata.source}
                        placeholder="e.g., Company Name, Publication"
                    />
                </div>

                <div class="form-group">
                    <label for="edit-weblink">Web Link</label>
                    <input
                        id="edit-weblink"
                        type="url"
                        bind:value={editMetadata.weblink}
                        placeholder="https://..."
                    />
                </div>
            </div>

            <div class="modal-footer">
                <button class="cancel-btn" on:click={closeEditModal} disabled={editSaving}>
                    Cancel
                </button>
                <button
                    class="save-btn"
                    on:click={saveEditedResource}
                    disabled={!editMetadata.title.trim() || editSaving}
                >
                    {editSaving ? 'Saving...' : 'Save Changes'}
                </button>
            </div>
        </div>
    </div>
{/if}

<!-- Content Edit Modal -->
{#if contentEditResource || contentEditLoading}
    <div class="modal-overlay content-edit-overlay" on:click={closeContentEditModal} role="dialog" aria-modal="true">
        <div class="modal content-edit-modal" on:click|stopPropagation>
            <div class="modal-header">
                <h3>Edit Content: {contentEditResource?.name || 'Loading...'}</h3>
                <button class="close-btn" on:click={closeContentEditModal}>×</button>
            </div>

            {#if contentEditLoading}
                <div class="modal-body loading-body">
                    <div class="spinner-small"></div>
                    <span>Loading content...</span>
                </div>
            {:else if contentEditResource}
                <div class="modal-body content-edit-body">
                    <!-- Text Content Editor -->
                    {#if contentEditResource.resource_type === 'text'}
                        <div class="text-editor">
                            <textarea
                                bind:value={contentEditValue}
                                placeholder="Enter text content..."
                                rows="20"
                            ></textarea>
                        </div>

                    <!-- Table Content Editor -->
                    {:else if contentEditResource.resource_type === 'table' && contentEditTableData}
                        <div class="table-editor">
                            <div class="table-actions">
                                <button class="table-action-btn" on:click={addTableRow}>+ Add Row</button>
                                <button class="table-action-btn" on:click={addTableColumn}>+ Add Column</button>
                            </div>
                            <div class="table-scroll">
                                <table>
                                    <thead>
                                        <tr>
                                            {#each contentEditTableData.columns as col, colIndex}
                                                <th>
                                                    <input
                                                        type="text"
                                                        value={col}
                                                        on:input={(e) => updateTableHeader(colIndex, e.currentTarget.value)}
                                                    />
                                                    <button class="col-remove" on:click={() => removeTableColumn(colIndex)} title="Remove column">×</button>
                                                </th>
                                            {/each}
                                            <th class="actions-col"></th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {#each contentEditTableData.data as row, rowIndex}
                                            <tr>
                                                {#each row as cell, colIndex}
                                                    <td>
                                                        <input
                                                            type="text"
                                                            value={cell}
                                                            on:input={(e) => updateTableCell(rowIndex, colIndex, e.currentTarget.value)}
                                                        />
                                                    </td>
                                                {/each}
                                                <td class="actions-col">
                                                    <button class="row-remove" on:click={() => removeTableRow(rowIndex)} title="Remove row">×</button>
                                                </td>
                                            </tr>
                                        {/each}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                    <!-- Timeseries Content Editor -->
                    {:else if contentEditResource.resource_type === 'timeseries' && contentEditTimeseriesData}
                        <div class="timeseries-editor">
                            <div class="table-actions">
                                <button class="table-action-btn" on:click={addTimeseriesRow}>+ Add Row</button>
                            </div>
                            <div class="table-scroll">
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Timestamp</th>
                                            {#if contentEditTimeseriesData.length > 0}
                                                {#each Object.keys(contentEditTimeseriesData[0].values) as key}
                                                    <th>{key}</th>
                                                {/each}
                                            {/if}
                                            <th class="actions-col"></th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {#each contentEditTimeseriesData as row, rowIndex}
                                            <tr>
                                                <td>
                                                    <input
                                                        type="text"
                                                        value={row.timestamp}
                                                        on:input={(e) => updateTimeseriesRow(rowIndex, 'timestamp', e.currentTarget.value)}
                                                    />
                                                </td>
                                                {#each Object.entries(row.values) as [key, value]}
                                                    <td>
                                                        <input
                                                            type="text"
                                                            value={value}
                                                            on:input={(e) => updateTimeseriesRow(rowIndex, key, e.currentTarget.value)}
                                                        />
                                                    </td>
                                                {/each}
                                                <td class="actions-col">
                                                    <button class="row-remove" on:click={() => removeTimeseriesRow(rowIndex)} title="Remove row">×</button>
                                                </td>
                                            </tr>
                                        {/each}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    {/if}
                </div>

                <div class="modal-footer">
                    <button class="cancel-btn" on:click={closeContentEditModal} disabled={contentEditSaving}>
                        Cancel
                    </button>
                    <button
                        class="save-btn"
                        on:click={saveEditedContent}
                        disabled={contentEditSaving}
                    >
                        {contentEditSaving ? 'Saving...' : 'Save Content'}
                    </button>
                </div>
            {/if}
        </div>
    </div>
{/if}

<style>
    .resource-editor {
        display: flex;
        flex-direction: column;
        gap: 1rem;
        outline: none;
    }

    .resource-editor:focus {
        outline: none;
    }

    /* Upload Controls */
    .upload-controls {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.75rem 1rem;
        background: #f9fafb;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        flex-wrap: wrap;
    }

    .upload-btn {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 1rem;
        background: #3b82f6;
        color: white;
        border-radius: 6px;
        cursor: pointer;
        font-size: 0.875rem;
        font-weight: 500;
        transition: background 0.2s;
    }

    .upload-btn:hover {
        background: #2563eb;
    }

    .upload-btn input {
        display: none;
    }

    .paste-hint {
        color: #6b7280;
        font-size: 0.75rem;
        margin-left: auto;
    }

    .upload-progress {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.75rem;
        padding: 1rem;
        color: #3b82f6;
        font-size: 0.875rem;
        background: #eff6ff;
        border-radius: 6px;
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

    /* Resource Sections */
    .resources-sections {
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
        flex: 1;
        overflow-y: auto;
    }

    .resource-section {
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        background: white;
        overflow: hidden;
    }

    .section-header-row {
        display: flex;
        align-items: center;
        background: #f9fafb;
        border-bottom: 1px solid #e5e7eb;
    }

    .section-header {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 0.75rem;
        background: transparent;
        border: none;
        cursor: pointer;
        flex: 1;
        text-align: left;
        font-family: inherit;
    }

    .section-header:hover {
        background: #f3f4f6;
    }

    .toggle-icon {
        font-size: 0.7rem;
        color: #6b7280;
        width: 1rem;
    }

    .section-title {
        font-weight: 600;
        font-size: 0.85rem;
        color: #374151;
    }

    .section-count {
        padding: 0.125rem 0.4rem;
        background: #e5e7eb;
        color: #4b5563;
        border-radius: 9999px;
        font-size: 0.7rem;
        font-weight: 500;
    }

    .section-count .available-count {
        color: #10b981;
        margin-left: 0.15rem;
    }

    .import-btn {
        padding: 0.25rem 0.5rem;
        margin-right: 0.5rem;
        background: #3b82f6;
        color: white;
        border: none;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 500;
        cursor: pointer;
        transition: background 0.2s;
    }

    .import-btn:hover {
        background: #2563eb;
    }

    .section-content {
        padding: 0.25rem 0.5rem 0.5rem 1.5rem;
    }

    .resources-loading,
    .no-resources {
        padding: 0.5rem;
        color: #9ca3af;
        font-size: 0.8rem;
        margin: 0;
    }

    .resources-list {
        display: flex;
        flex-direction: column;
        gap: 0.125rem;
    }

    .resource-item {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.375rem 0.5rem;
        border-radius: 4px;
        transition: background 0.15s;
    }

    .resource-item:hover {
        background: #f3f4f6;
    }

    .resource-icon {
        font-size: 1rem;
        flex-shrink: 0;
    }

    .resource-name {
        font-size: 0.8rem;
        color: #1f2937;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        flex: 1;
        min-width: 0;
    }

    .resource-type-badge {
        padding: 0.1rem 0.3rem;
        background: #e5e7eb;
        color: #6b7280;
        border-radius: 3px;
        font-size: 0.6rem;
        text-transform: uppercase;
        font-weight: 500;
        flex-shrink: 0;
    }

    .resource-actions {
        display: flex;
        gap: 0.25rem;
        flex-shrink: 0;
        opacity: 0;
        transition: opacity 0.15s;
    }

    .resource-item:hover .resource-actions {
        opacity: 1;
    }

    .action-btn {
        width: 22px;
        height: 22px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #f3f4f6;
        border: none;
        color: #6b7280;
        font-size: 0.75rem;
        cursor: pointer;
        border-radius: 3px;
        transition: all 0.15s;
    }

    .action-btn:hover {
        background: #e5e7eb;
        color: #374151;
    }

    .action-btn.remove:hover {
        background: #fee2e2;
        color: #dc2626;
    }

    .action-btn.publish:hover {
        background: #d1fae5;
        color: #059669;
    }

    .action-btn.recall:hover {
        background: #fef3c7;
        color: #d97706;
    }

    .draggable-resource {
        cursor: grab;
    }

    .draggable-resource:active {
        cursor: grabbing;
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

    .import-modal {
        max-width: 600px;
        max-height: 80vh;
        display: flex;
        flex-direction: column;
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
        overflow-y: auto;
        flex: 1;
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

    /* Import Modal Styles */
    .import-search input {
        width: 100%;
        padding: 0.75rem;
        border: 1px solid #e0e0e0;
        border-radius: 6px;
        font-size: 0.9rem;
    }

    .import-search input:focus {
        outline: none;
        border-color: #3b82f6;
    }

    .import-tabs {
        display: flex;
        gap: 0.5rem;
        border-bottom: 1px solid #e5e7eb;
        padding-bottom: 0.5rem;
    }

    .import-tab {
        padding: 0.5rem 1rem;
        background: none;
        border: none;
        color: #6b7280;
        font-size: 0.875rem;
        font-weight: 500;
        cursor: pointer;
        border-radius: 4px;
        transition: all 0.2s;
    }

    .import-tab:hover:not(:disabled) {
        background: #f3f4f6;
        color: #1f2937;
    }

    .import-tab.active {
        background: #3b82f6;
        color: white;
    }

    .import-tab:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .import-list {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        max-height: 400px;
        overflow-y: auto;
    }

    .import-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.75rem;
        background: #f9fafb;
        border: 1px solid #e5e7eb;
        border-radius: 6px;
        gap: 1rem;
    }

    .import-item:hover {
        border-color: #d1d5db;
    }

    .import-item-info {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        flex: 1;
        min-width: 0;
    }

    .import-item-details {
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
        min-width: 0;
    }

    .import-item-details .resource-name {
        font-size: 0.9rem;
    }

    .import-item-desc {
        font-size: 0.75rem;
        color: #6b7280;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .import-item-actions {
        display: flex;
        gap: 0.5rem;
        flex-shrink: 0;
    }

    /* Preview Modal Styles */
    .preview-overlay {
        z-index: 1001;
    }

    .preview-modal {
        width: 90vw;
        max-width: 1200px;
        height: 85vh;
        max-height: 900px;
        display: flex;
        flex-direction: column;
    }

    .preview-modal .modal-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1rem 1.5rem;
        border-bottom: 1px solid #e5e7eb;
        flex-shrink: 0;
    }

    .preview-modal .modal-header h3 {
        margin: 0;
        font-size: 1.1rem;
        color: #1a1a1a;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        flex: 1;
        margin-right: 1rem;
    }

    .preview-actions {
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .open-external-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        background: #f3f4f6;
        color: #374151;
        text-decoration: none;
        border-radius: 6px;
        font-size: 1.1rem;
        transition: all 0.2s;
    }

    .open-external-btn:hover {
        background: #e5e7eb;
        color: #1a1a1a;
    }

    .preview-content {
        flex: 1;
        overflow: auto;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #f9fafb;
        padding: 1rem;
    }

    .preview-image {
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
        border-radius: 4px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    }

    .preview-pdf,
    .preview-text,
    .preview-article,
    .preview-table-html {
        width: 100%;
        height: 100%;
        border: none;
        border-radius: 4px;
        background: white;
    }

    /* Table Preview Styles */
    .table-loading {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 1rem;
        padding: 3rem;
        color: #6b7280;
    }

    .preview-table-container {
        width: 100%;
        height: 100%;
        overflow: auto;
        background: white;
        border-radius: 6px;
        border: 1px solid #e5e7eb;
    }

    .preview-data-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.875rem;
    }

    .preview-data-table thead {
        position: sticky;
        top: 0;
        z-index: 1;
    }

    .preview-data-table th {
        background: #f8fafc;
        border-bottom: 2px solid #e2e8f0;
        padding: 0.75rem 1rem;
        text-align: left;
        font-weight: 600;
        color: #334155;
        white-space: nowrap;
    }

    .sortable-header {
        cursor: pointer;
        user-select: none;
        transition: background 0.15s;
    }

    .sortable-header:hover {
        background: #f1f5f9;
    }

    .header-text {
        margin-right: 0.5rem;
    }

    .sort-indicator {
        font-size: 0.7rem;
        color: #3b82f6;
    }

    .sort-inactive {
        color: #cbd5e1;
    }

    .preview-data-table td {
        padding: 0.625rem 1rem;
        border-bottom: 1px solid #f1f5f9;
        color: #475569;
    }

    .preview-data-table tbody tr:hover {
        background: #f8fafc;
    }

    .preview-data-table tbody tr:nth-child(even) {
        background: #fafbfc;
    }

    .preview-data-table tbody tr:nth-child(even):hover {
        background: #f1f5f9;
    }

    .preview-unsupported {
        text-align: center;
        padding: 2rem;
        color: #6b7280;
    }

    .preview-unsupported p {
        margin: 0 0 1rem 0;
    }

    .download-link {
        display: inline-block;
        padding: 0.5rem 1rem;
        background: #3b82f6;
        color: white;
        text-decoration: none;
        border-radius: 6px;
        font-weight: 500;
        transition: background 0.2s;
    }

    .download-link:hover {
        background: #2563eb;
    }

    /* Content Edit Modal Styles */
    .content-edit-overlay {
        z-index: 1002;
    }

    .content-edit-modal {
        width: 90vw;
        max-width: 1200px;
        height: 85vh;
        max-height: 900px;
        display: flex;
        flex-direction: column;
    }

    .loading-body {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 1rem;
        padding: 3rem;
        color: #6b7280;
    }

    .content-edit-body {
        flex: 1;
        overflow: hidden;
        padding: 1rem;
        display: flex;
        flex-direction: column;
    }

    /* Text Editor */
    .text-editor {
        flex: 1;
        display: flex;
        flex-direction: column;
    }

    .text-editor textarea {
        flex: 1;
        width: 100%;
        padding: 1rem;
        border: 1px solid #e5e7eb;
        border-radius: 6px;
        font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
        font-size: 0.9rem;
        line-height: 1.5;
        resize: none;
    }

    .text-editor textarea:focus {
        outline: none;
        border-color: #3b82f6;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
    }

    /* Table Editor */
    .table-editor,
    .timeseries-editor {
        flex: 1;
        display: flex;
        flex-direction: column;
        overflow: hidden;
    }

    .table-actions {
        display: flex;
        gap: 0.5rem;
        margin-bottom: 0.75rem;
        flex-shrink: 0;
    }

    .table-action-btn {
        padding: 0.375rem 0.75rem;
        background: #f3f4f6;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        font-size: 0.8rem;
        cursor: pointer;
        transition: all 0.2s;
    }

    .table-action-btn:hover {
        background: #e5e7eb;
        border-color: #d1d5db;
    }

    .table-scroll {
        flex: 1;
        overflow: auto;
        border: 1px solid #e5e7eb;
        border-radius: 6px;
        background: white;
    }

    .table-editor table,
    .timeseries-editor table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.85rem;
    }

    .table-editor th,
    .timeseries-editor th {
        background: #f9fafb;
        border-bottom: 2px solid #e5e7eb;
        padding: 0;
        position: sticky;
        top: 0;
        z-index: 1;
    }

    .table-editor th input,
    .timeseries-editor th:not(.actions-col) {
        padding: 0.5rem;
        font-weight: 600;
        color: #374151;
    }

    .table-editor th input {
        width: 100%;
        border: none;
        background: transparent;
        font-weight: 600;
        font-size: 0.85rem;
        padding: 0.5rem;
    }

    .table-editor th input:focus {
        outline: none;
        background: #eff6ff;
    }

    .col-remove {
        position: absolute;
        right: 2px;
        top: 50%;
        transform: translateY(-50%);
        width: 18px;
        height: 18px;
        padding: 0;
        border: none;
        background: transparent;
        color: #9ca3af;
        font-size: 0.9rem;
        cursor: pointer;
        display: none;
    }

    .table-editor th {
        position: relative;
    }

    .table-editor th:hover .col-remove {
        display: block;
    }

    .col-remove:hover {
        color: #dc2626;
    }

    .table-editor td,
    .timeseries-editor td {
        border-bottom: 1px solid #f3f4f6;
        padding: 0;
    }

    .table-editor td input,
    .timeseries-editor td input {
        width: 100%;
        border: none;
        padding: 0.5rem;
        font-size: 0.85rem;
        background: transparent;
    }

    .table-editor td input:focus,
    .timeseries-editor td input:focus {
        outline: none;
        background: #eff6ff;
    }

    .actions-col {
        width: 40px;
        text-align: center;
    }

    .row-remove {
        width: 22px;
        height: 22px;
        padding: 0;
        border: none;
        background: transparent;
        color: #9ca3af;
        font-size: 1rem;
        cursor: pointer;
        opacity: 0;
        transition: opacity 0.15s;
    }

    .table-editor tr:hover .row-remove,
    .timeseries-editor tr:hover .row-remove {
        opacity: 1;
    }

    .row-remove:hover {
        color: #dc2626;
    }
</style>
