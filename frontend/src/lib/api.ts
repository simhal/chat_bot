import { get } from 'svelte/store';
import { auth } from './stores/auth';
import { PUBLIC_API_URL } from '$env/static/public';

let isRefreshing = false;
let refreshSubscribers: Array<(token: string) => void> = [];

function onRefreshed(token: string) {
    refreshSubscribers.forEach(callback => callback(token));
    refreshSubscribers = [];
}

function addRefreshSubscriber(callback: (token: string) => void) {
    refreshSubscribers.push(callback);
}

async function refreshAccessToken(): Promise<string | null> {
    const authState = get(auth);

    if (!authState.refreshToken) {
        return null;
    }

    try {
        const response = await fetch(`${PUBLIC_API_URL}/api/auth/refresh`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                refresh_token: authState.refreshToken
            })
        });

        if (!response.ok) {
            auth.logout();
            return null;
        }

        const data = await response.json();
        auth.updateTokens(data.access_token, data.refresh_token);
        return data.access_token;
    } catch (error) {
        console.error('Failed to refresh token:', error);
        auth.logout();
        return null;
    }
}

export async function apiRequest(endpoint: string, options: RequestInit = {}) {
    const authState = get(auth);

    const headers = new Headers(options.headers);

    if (authState.accessToken) {
        headers.set('Authorization', `Bearer ${authState.accessToken}`);
    }

    headers.set('Content-Type', 'application/json');

    const response = await fetch(`${PUBLIC_API_URL}${endpoint}`, {
        ...options,
        headers
    });

    // Handle 401 - token might be expired
    if (response.status === 401 && authState.refreshToken) {
        if (!isRefreshing) {
            isRefreshing = true;
            const newToken = await refreshAccessToken();
            isRefreshing = false;

            if (newToken) {
                onRefreshed(newToken);

                // Retry the original request with new token
                headers.set('Authorization', `Bearer ${newToken}`);
                const retryResponse = await fetch(`${PUBLIC_API_URL}${endpoint}`, {
                    ...options,
                    headers
                });

                if (!retryResponse.ok) {
                    const error = await retryResponse.json().catch(() => ({ detail: 'Unknown error' }));
                    throw new Error(error.detail || `API error: ${retryResponse.status}`);
                }

                return retryResponse.json();
            } else {
                throw new Error('Session expired. Please log in again.');
            }
        } else {
            // Wait for the ongoing refresh to complete
            return new Promise((resolve, reject) => {
                addRefreshSubscriber(async (token: string) => {
                    headers.set('Authorization', `Bearer ${token}`);
                    try {
                        const retryResponse = await fetch(`${PUBLIC_API_URL}${endpoint}`, {
                            ...options,
                            headers
                        });

                        if (!retryResponse.ok) {
                            const error = await retryResponse.json().catch(() => ({ detail: 'Unknown error' }));
                            reject(new Error(error.detail || `API error: ${retryResponse.status}`));
                        }

                        const data = await retryResponse.json();
                        resolve(data);
                    } catch (error) {
                        reject(error);
                    }
                });
            });
        }
    }

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(error.detail || `API error: ${response.status}`);
    }

    return response.json();
}

export async function sendChatMessage(message: string) {
    return apiRequest('/api/chat', {
        method: 'POST',
        body: JSON.stringify({ message })
    });
}

export async function getUserInfo() {
    return apiRequest('/api/me');
}

export async function logout(refreshToken: string | null) {
    return apiRequest('/api/auth/logout', {
        method: 'POST',
        body: JSON.stringify({ refresh_token: refreshToken })
    });
}

// Admin API functions
export async function getAdminUsers() {
    return apiRequest('/api/admin/users');
}

export async function createUser(email: string, name?: string, surname?: string) {
    return apiRequest('/api/admin/users', {
        method: 'POST',
        body: JSON.stringify({ email, name, surname })
    });
}

export async function banUser(userId: number) {
    return apiRequest(`/api/admin/users/${userId}/ban`, {
        method: 'PUT'
    });
}

export async function unbanUser(userId: number) {
    return apiRequest(`/api/admin/users/${userId}/unban`, {
        method: 'PUT'
    });
}

export async function deleteUser(userId: number) {
    return apiRequest(`/api/admin/users/${userId}`, {
        method: 'DELETE'
    });
}

export async function getAdminGroups() {
    return apiRequest('/api/admin/groups');
}

export async function assignGroupToUser(userId: number, groupName: string) {
    return apiRequest(`/api/admin/users/${userId}/groups`, {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, group_name: groupName })
    });
}

export async function removeGroupFromUser(userId: number, groupName: string) {
    return apiRequest(`/api/admin/users/${userId}/groups/${groupName}`, {
        method: 'DELETE'
    });
}

export async function createGroup(name: string, description?: string) {
    return apiRequest('/api/admin/groups', {
        method: 'POST',
        body: JSON.stringify({ name, description })
    });
}

// Content management API functions
export async function getAdminArticles(topic: string, offset: number = 0, limit: number = 20) {
    return apiRequest(`/api/content/admin/articles/${topic}?offset=${offset}&limit=${limit}`);
}

export async function deleteArticle(articleId: number) {
    return apiRequest(`/api/content/admin/article/${articleId}`, {
        method: 'DELETE'
    });
}

export async function reactivateArticle(articleId: number) {
    return apiRequest(`/api/content/admin/article/${articleId}/reactivate`, {
        method: 'POST'
    });
}

export async function recallArticle(articleId: number) {
    return apiRequest(`/api/content/admin/article/${articleId}/recall`, {
        method: 'POST'
    });
}

export async function purgeArticle(articleId: number) {
    return apiRequest(`/api/content/admin/article/${articleId}/purge`, {
        method: 'DELETE'
    });
}

export async function rateArticle(articleId: number, rating: number) {
    return apiRequest(`/api/content/article/${articleId}/rate`, {
        method: 'POST',
        body: JSON.stringify({ rating })
    });
}

export async function editArticle(
    articleId: number,
    headline?: string,
    content?: string,
    keywords?: string,
    status?: string,
    priority?: number,
    is_sticky?: boolean
) {
    return apiRequest(`/api/content/article/${articleId}/edit`, {
        method: 'PUT',
        body: JSON.stringify({ headline, content, keywords, status, priority, is_sticky })
    });
}

// Reorder articles (admin only) - bulk update priorities
export async function reorderArticles(articles: Array<{ id: number; priority: number }>): Promise<{ message: string; updated: number[] }> {
    return apiRequest('/api/content/admin/articles/reorder', {
        method: 'POST',
        body: JSON.stringify({ articles })
    });
}

export async function generateContent(topic: string, query: string) {
    return apiRequest(`/api/content/generate/${topic}`, {
        method: 'POST',
        body: JSON.stringify({ query })
    });
}

export async function createEmptyArticle(topic: string, headline?: string): Promise<{ id: number }> {
    return apiRequest(`/api/content/article/new/${topic}`, {
        method: 'POST',
        body: JSON.stringify({ headline: headline || 'New Article' })
    });
}

export interface SearchParams {
    q?: string;
    headline?: string;
    keywords?: string;
    author?: string;
    created_after?: string;
    created_before?: string;
    limit?: number;
}

export async function searchArticles(topic: string, params: SearchParams) {
    const queryParams = new URLSearchParams();

    if (params.q) queryParams.append('q', params.q);
    if (params.headline) queryParams.append('headline', params.headline);
    if (params.keywords) queryParams.append('keywords', params.keywords);
    if (params.author) queryParams.append('author', params.author);
    if (params.created_after) queryParams.append('created_after', params.created_after);
    if (params.created_before) queryParams.append('created_before', params.created_before);
    if (params.limit) queryParams.append('limit', params.limit.toString());

    const query = queryParams.toString();
    return apiRequest(`/api/content/search/${topic}${query ? '?' + query : ''}`);
}

export async function chatWithContentAgent(
    articleId: number,
    message: string,
    currentHeadline: string,
    currentContent: string,
    currentKeywords?: string
) {
    return apiRequest(`/api/content/article/${articleId}/chat`, {
        method: 'POST',
        body: JSON.stringify({
            message,
            current_headline: currentHeadline,
            current_content: currentContent,
            current_keywords: currentKeywords
        })
    });
}

export async function getArticle(articleId: number) {
    return apiRequest(`/api/content/article/${articleId}`);
}

export async function downloadArticlePDF(articleId: number) {
    const authState = get(auth);

    const headers = new Headers();
    if (authState.accessToken) {
        headers.set('Authorization', `Bearer ${authState.accessToken}`);
    }

    const response = await fetch(`${PUBLIC_API_URL}/api/content/article/${articleId}/pdf`, {
        method: 'GET',
        headers
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Failed to download PDF' }));
        throw new Error(error.detail || `Failed to download PDF: ${response.status}`);
    }

    // Get the filename from the Content-Disposition header
    const contentDisposition = response.headers.get('Content-Disposition');
    let filename = `article_${articleId}.pdf`;
    if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename=(.+)/);
        if (filenameMatch) {
            filename = filenameMatch[1].replace(/['"]/g, '');
        }
    }

    // Get the blob and create a download link
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

// User Profile API functions
export async function getUserProfile() {
    return apiRequest('/api/profile/me');
}

export async function deleteUserAccount() {
    return apiRequest('/api/profile/me', {
        method: 'DELETE'
    });
}

// Editorial workflow API functions
export async function getAnalystDraftArticles(topic: string, offset: number = 0, limit: number = 20) {
    return apiRequest(`/api/content/analyst/articles/${topic}?offset=${offset}&limit=${limit}`);
}

export async function getEditorArticles(topic: string, offset: number = 0, limit: number = 20) {
    return apiRequest(`/api/content/editor/articles/${topic}?offset=${offset}&limit=${limit}`);
}

export async function getPublishedArticles(topic: string, limit: number = 10) {
    return apiRequest(`/api/content/published/articles/${topic}?limit=${limit}`);
}

export async function approveArticle(articleId: number) {
    return apiRequest(`/api/content/article/${articleId}/approve`, {
        method: 'POST'
    });
}

export async function rejectArticle(articleId: number) {
    return apiRequest(`/api/content/article/${articleId}/reject`, {
        method: 'POST'
    });
}

export async function publishArticle(articleId: number) {
    return apiRequest(`/api/content/article/${articleId}/publish`, {
        method: 'POST'
    });
}

// Prompt Module API functions
export interface PromptModule {
    id: number;
    name: string;
    prompt_type: string;
    prompt_group: string | null;
    template_text: string;
    description: string | null;
    is_default: boolean;
    sort_order: number;
    is_active: boolean;
    version: number;
    created_at: string | null;
    updated_at: string | null;
}

export interface TonalityPreferences {
    chat_tonality: { id: number; name: string; description: string } | null;
    content_tonality: { id: number; name: string; description: string } | null;
}

export interface TonalityOption {
    id: number;
    name: string;
    description: string | null;
    prompt_group: string | null;
    is_default: boolean;
}

export async function getPromptModules(promptType?: string, promptGroup?: string) {
    let url = '/api/prompts?active_only=true';
    if (promptType) url += `&prompt_type=${promptType}`;
    if (promptGroup) url += `&prompt_group=${promptGroup}`;
    return apiRequest(url);
}

export async function getTonalities(): Promise<TonalityOption[]> {
    return apiRequest('/api/prompts/tonalities');
}

export async function getPromptModule(moduleId: number): Promise<PromptModule> {
    return apiRequest(`/api/prompts/${moduleId}`);
}

export async function updatePromptModule(moduleId: number, templateText: string, name?: string, description?: string) {
    return apiRequest(`/api/prompts/${moduleId}`, {
        method: 'PUT',
        body: JSON.stringify({
            template_text: templateText,
            name,
            description
        })
    });
}

export async function createTonality(name: string, templateText: string, description?: string, promptGroup?: string, sortOrder?: number) {
    return apiRequest('/api/prompts/tonality', {
        method: 'POST',
        body: JSON.stringify({
            name,
            template_text: templateText,
            description,
            prompt_group: promptGroup,
            sort_order: sortOrder || 99
        })
    });
}

export async function createContentAgent(name: string, templateText: string, promptGroup: string, description?: string, sortOrder?: number) {
    return apiRequest('/api/prompts/content-agent', {
        method: 'POST',
        body: JSON.stringify({
            name,
            template_text: templateText,
            prompt_group: promptGroup,
            description,
            sort_order: sortOrder || 99
        })
    });
}

export async function deleteTonality(moduleId: number) {
    return apiRequest(`/api/prompts/${moduleId}`, {
        method: 'DELETE'
    });
}

export async function setDefaultTonality(moduleId: number) {
    return apiRequest(`/api/prompts/tonality/${moduleId}/set-default`, {
        method: 'POST'
    });
}

export async function getUserTonality(): Promise<TonalityPreferences> {
    return apiRequest('/api/prompts/user/tonality');
}

export async function updateUserTonality(chatTonalityId: number | null, contentTonalityId: number | null) {
    return apiRequest('/api/prompts/user/tonality', {
        method: 'PUT',
        body: JSON.stringify({
            chat_tonality_id: chatTonalityId,
            content_tonality_id: contentTonalityId
        })
    });
}

// Admin endpoints for user tonality management
export async function adminGetUserTonality(userId: number): Promise<TonalityPreferences> {
    return apiRequest(`/api/prompts/admin/user/${userId}/tonality`);
}

export async function adminUpdateUserTonality(userId: number, chatTonalityId: number | null, contentTonalityId: number | null) {
    return apiRequest(`/api/prompts/admin/user/${userId}/tonality`, {
        method: 'PUT',
        body: JSON.stringify({
            chat_tonality_id: chatTonalityId,
            content_tonality_id: contentTonalityId
        })
    });
}

// =============================================================================
// Resource Management API functions
// =============================================================================

export interface Resource {
    id: number;
    hash_id: string;  // URL-safe public ID for content URLs
    resource_type: string;
    status: string;  // draft, editor, published
    name: string;
    description: string | null;
    group_id: number | null;
    created_by: number | null;
    modified_by: number | null;
    created_at: string | null;
    updated_at: string | null;
    is_active: boolean;
}

export interface ChildResourceInfo {
    id: number;
    hash_id: string;
    resource_type: string;
    name: string;
}

export interface ResourceDetail extends Resource {
    children?: ChildResourceInfo[];
    file_data?: {
        filename: string;
        file_path: string;
        file_size: number;
        mime_type: string;
        checksum: string | null;
    };
    text_data?: {
        content: string;
        encoding: string;
        char_count: number;
        word_count: number;
        chromadb_id: string | null;
    };
    table_data?: {
        data: { columns: string[]; data: any[][] };
        row_count: number;
        column_count: number;
        column_names: string[];
        column_types: Record<string, string> | null;
        chromadb_id: string | null;
    };
    timeseries_data?: {
        tsid: number;
        name: string;
        source: string | null;
        frequency: string;
        data_type: string;
        columns: string[];
        start_date: string | null;
        end_date: string | null;
        data_point_count: number;
        unit: string | null;
    };
}

export interface ResourceListResponse {
    resources: Resource[];
    total: number;
    offset: number;
    limit: number;
}

// List resources for a specific topic group
export async function getGroupResources(
    topic: string,
    resourceType?: string,
    search?: string,
    offset: number = 0,
    limit: number = 50
): Promise<ResourceListResponse> {
    const params = new URLSearchParams();
    if (resourceType) params.append('resource_type', resourceType);
    if (search) params.append('search', search);
    params.append('offset', offset.toString());
    params.append('limit', limit.toString());

    const query = params.toString();
    return apiRequest(`/api/resources/group/${topic}${query ? '?' + query : ''}`);
}

// List global resources (no group)
export async function getGlobalResources(
    resourceType?: string,
    search?: string,
    offset: number = 0,
    limit: number = 50,
    includeLinked: boolean = true
): Promise<ResourceListResponse> {
    const params = new URLSearchParams();
    if (resourceType) params.append('resource_type', resourceType);
    if (search) params.append('search', search);
    params.append('offset', offset.toString());
    params.append('limit', limit.toString());
    params.append('include_linked', includeLinked.toString());

    const query = params.toString();
    return apiRequest(`/api/resources/global${query ? '?' + query : ''}`);
}

// Get single resource with details
export async function getResource(resourceId: number): Promise<ResourceDetail> {
    return apiRequest(`/api/resources/${resourceId}`);
}

// Create text resource
export async function createTextResource(
    name: string,
    content: string,
    groupId?: number,
    description?: string,
    groupName?: string
): Promise<ResourceDetail> {
    return apiRequest('/api/resources/text', {
        method: 'POST',
        body: JSON.stringify({
            name,
            content,
            group_id: groupId,
            group_name: groupName,
            description
        })
    });
}

// Create table resource
export async function createTableResource(
    name: string,
    tableData: { columns: string[]; data: any[][] },
    groupId?: number,
    description?: string,
    columnTypes?: Record<string, string>,
    groupName?: string
): Promise<ResourceDetail> {
    return apiRequest('/api/resources/table', {
        method: 'POST',
        body: JSON.stringify({
            name,
            table_data: tableData,
            group_id: groupId,
            group_name: groupName,
            description,
            column_types: columnTypes
        })
    });
}

// Create timeseries resource
export async function createTimeseriesResource(
    name: string,
    columns: string[],
    frequency: string,
    groupId?: number,
    description?: string,
    source?: string,
    dataType: string = 'float',
    unit?: string
): Promise<ResourceDetail> {
    return apiRequest('/api/resources/timeseries', {
        method: 'POST',
        body: JSON.stringify({
            name,
            columns,
            frequency,
            group_id: groupId,
            description,
            source,
            data_type: dataType,
            unit
        })
    });
}

// Update resource metadata
export async function updateResource(
    resourceId: number,
    name?: string,
    description?: string,
    groupId?: number
): Promise<ResourceDetail> {
    return apiRequest(`/api/resources/${resourceId}`, {
        method: 'PUT',
        body: JSON.stringify({
            name,
            description,
            group_id: groupId
        })
    });
}

// Delete resource
export async function deleteResource(resourceId: number): Promise<{ message: string; id: number }> {
    return apiRequest(`/api/resources/${resourceId}`, {
        method: 'DELETE'
    });
}

// Add timeseries data
export async function addTimeseriesData(
    resourceId: number,
    dataPoints: Array<{ date: string; column_name: string; value?: number; value_str?: string }>
): Promise<{ message: string; count: number }> {
    return apiRequest(`/api/resources/${resourceId}/timeseries/data`, {
        method: 'POST',
        body: JSON.stringify({ data_points: dataPoints })
    });
}

// Get timeseries data
export async function getTimeseriesData(
    resourceId: number,
    startDate?: string,
    endDate?: string,
    columns?: string[]
): Promise<{ data: any[]; count: number }> {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    if (columns && columns.length > 0) params.append('columns', columns.join(','));

    const query = params.toString();
    return apiRequest(`/api/resources/${resourceId}/timeseries/data${query ? '?' + query : ''}`);
}

// Link resource to article
export async function linkResourceToArticle(resourceId: number, articleId: number): Promise<{ message: string }> {
    return apiRequest(`/api/resources/${resourceId}/link`, {
        method: 'POST',
        body: JSON.stringify({ article_id: articleId })
    });
}

// Unlink resource from article
export async function unlinkResourceFromArticle(resourceId: number, articleId: number): Promise<{ message: string }> {
    return apiRequest(`/api/resources/${resourceId}/link/${articleId}`, {
        method: 'DELETE'
    });
}

// Update resource status (editorial workflow)
export async function updateResourceStatus(resourceId: number, status: string): Promise<ResourceDetail> {
    return apiRequest(`/api/resources/${resourceId}/status`, {
        method: 'PUT',
        body: JSON.stringify({ status })
    });
}

// Publish a table resource (creates HTML/IMAGE children)
export async function publishTableResource(resourceId: number): Promise<ResourceDetail> {
    return apiRequest(`/api/resources/${resourceId}/publish`, {
        method: 'POST'
    });
}

// Recall a published table resource (deletes children, returns to draft)
export async function recallTableResource(resourceId: number): Promise<ResourceDetail> {
    return apiRequest(`/api/resources/${resourceId}/recall`, {
        method: 'POST'
    });
}

// Update text resource content
export async function updateTextContent(
    resourceId: number,
    content: string,
    encoding: string = 'utf-8'
): Promise<ResourceDetail> {
    return apiRequest(`/api/resources/${resourceId}/text-content`, {
        method: 'PUT',
        body: JSON.stringify({ content, encoding })
    });
}

// Update table resource content
export async function updateTableContent(
    resourceId: number,
    tableData: { columns: string[]; data: any[][] },
    columnTypes?: Record<string, string>
): Promise<ResourceDetail> {
    return apiRequest(`/api/resources/${resourceId}/table-content`, {
        method: 'PUT',
        body: JSON.stringify({ table_data: tableData, column_types: columnTypes })
    });
}

// Update timeseries data
export async function updateTimeseriesData(
    resourceId: number,
    data: Array<{ timestamp: string; values: Record<string, any> }>
): Promise<ResourceDetail> {
    return apiRequest(`/api/resources/${resourceId}/timeseries-data`, {
        method: 'PUT',
        body: JSON.stringify({ data })
    });
}

// Get articles linked to a resource
export async function getResourceArticles(resourceId: number): Promise<{ articles: any[]; count: number }> {
    return apiRequest(`/api/resources/${resourceId}/articles`);
}

// Get resources linked to an article
export async function getArticleResources(articleId: number): Promise<{ resources: Resource[]; count: number }> {
    return apiRequest(`/api/resources/article/${articleId}`);
}

/**
 * Get the public URL for accessing resource content directly.
 * This URL can be used in HTML img tags, links, etc.
 * Example: <img src={getResourceContentUrl(resource.hash_id)} />
 */
export function getResourceContentUrl(hashId: string): string {
    return `${PUBLIC_API_URL}/api/resources/content/${hashId}`;
}

/**
 * Resource info returned by the public info endpoint.
 */
export interface ResourceInfo {
    hash_id: string;
    name: string;
    resource_type: string;
    status: string;
}

/**
 * Get public info about a resource by hash_id.
 * This is a public endpoint - no authentication required.
 * Useful for rendering resource links in markdown previews.
 */
export async function getResourceInfo(hashId: string): Promise<ResourceInfo> {
    const response = await fetch(`${PUBLIC_API_URL}/api/resources/content/${hashId}/info`);
    if (!response.ok) {
        throw new Error('Resource not found');
    }
    return response.json();
}

// Create text resource and link to article
export async function createTextResourceForArticle(
    name: string,
    content: string,
    articleId: number,
    description?: string
): Promise<ResourceDetail> {
    const resource = await createTextResource(name, content, undefined, description);
    await linkResourceToArticle(resource.id, articleId);
    return resource;
}

// Create table resource and link to article
export async function createTableResourceForArticle(
    name: string,
    tableData: { columns: string[]; data: any[][] },
    articleId: number,
    description?: string
): Promise<ResourceDetail> {
    const resource = await createTableResource(name, tableData, undefined, description);
    await linkResourceToArticle(resource.id, articleId);
    return resource;
}

// Upload a file resource (with optional article linking)
export async function uploadFileResource(
    file: File,
    name: string,
    articleId?: number,
    groupId?: number,
    description?: string,
    groupName?: string
): Promise<ResourceDetail> {
    const authState = get(auth);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', name);
    if (articleId) formData.append('article_id', articleId.toString());
    if (groupId) formData.append('group_id', groupId.toString());
    if (groupName) formData.append('group_name', groupName);
    if (description) formData.append('description', description);

    const headers = new Headers();
    if (authState.accessToken) {
        headers.set('Authorization', `Bearer ${authState.accessToken}`);
    }
    // Note: Don't set Content-Type for FormData - browser will set it with boundary

    const response = await fetch(`${PUBLIC_API_URL}/api/resources/file`, {
        method: 'POST',
        headers,
        body: formData
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
        throw new Error(error.detail || `Upload failed: ${response.status}`);
    }

    return response.json();
}

// =============================================================================
// Topic Management API functions
// =============================================================================

export interface Topic {
    id: number;
    slug: string;
    title: string;
    description: string | null;
    visible: boolean;
    searchable?: boolean;
    active: boolean;
    reader_count?: number;
    rating_average?: number | null;
    article_count: number;
    agent_type?: string | null;
    agent_config?: Record<string, any> | null;
    access_mainchat: boolean;
    icon: string | null;
    color: string | null;
    sort_order: number;
    article_order: string;  // 'date', 'priority', 'title'
    created_at?: string;
    updated_at?: string;
}

export interface TopicCreate {
    slug: string;
    title: string;
    description?: string;
    visible?: boolean;
    searchable?: boolean;
    active?: boolean;
    agent_type?: string;
    agent_config?: Record<string, any>;
    access_mainchat?: boolean;
    icon?: string;
    color?: string;
    sort_order?: number;
    article_order?: string;  // 'date', 'priority', 'title'
}

export interface TopicUpdate {
    title?: string;
    description?: string;
    visible?: boolean;
    searchable?: boolean;
    active?: boolean;
    agent_type?: string;
    agent_config?: Record<string, any>;
    access_mainchat?: boolean;
    icon?: string;
    color?: string;
    sort_order?: number;
    article_order?: string;  // 'date', 'priority', 'title'
}

// Get all topics (authenticated)
export async function getTopics(activeOnly: boolean = false, visibleOnly: boolean = false): Promise<Topic[]> {
    const params = new URLSearchParams();
    if (activeOnly) params.append('active_only', 'true');
    if (visibleOnly) params.append('visible_only', 'true');
    const query = params.toString();
    return apiRequest(`/api/topics${query ? '?' + query : ''}`);
}

// Get public topics (no auth required)
export async function getPublicTopics(): Promise<Topic[]> {
    const response = await fetch(`${PUBLIC_API_URL}/api/topics/public`);
    if (!response.ok) {
        throw new Error('Failed to fetch topics');
    }
    return response.json();
}

// Get a single topic by slug
export async function getTopic(slug: string): Promise<Topic> {
    return apiRequest(`/api/topics/${slug}`);
}

// Create a new topic (admin only)
export async function createTopic(topic: TopicCreate): Promise<Topic> {
    return apiRequest('/api/topics', {
        method: 'POST',
        body: JSON.stringify(topic)
    });
}

// Update a topic (admin only)
export async function updateTopic(slug: string, updates: TopicUpdate): Promise<Topic> {
    return apiRequest(`/api/topics/${slug}`, {
        method: 'PATCH',
        body: JSON.stringify(updates)
    });
}

// Delete a topic (admin only)
export async function deleteTopic(slug: string, force: boolean = false): Promise<{ message: string; deleted_id: number }> {
    const params = force ? '?force=true' : '';
    return apiRequest(`/api/topics/${slug}${params}`, {
        method: 'DELETE'
    });
}

// Recalculate topic stats (admin only)
export async function recalculateTopicStats(slug: string): Promise<{ message: string; article_count: number; reader_count: number; rating_average: number | null }> {
    return apiRequest(`/api/topics/${slug}/recalculate-stats`, {
        method: 'POST'
    });
}

// Recalculate all topic stats (admin only)
export async function recalculateAllTopicStats(): Promise<{ message: string; count: number }> {
    return apiRequest('/api/topics/recalculate-all', {
        method: 'POST'
    });
}

// Reorder topics (admin only) - bulk update sort_order
export async function reorderTopics(topics: Array<{ slug: string; sort_order: number }>): Promise<{ message: string; updated: string[] }> {
    return apiRequest('/api/topics/reorder', {
        method: 'POST',
        body: JSON.stringify({ topics })
    });
}

// Get groups for a topic (admin only)
export async function getTopicGroups(slug: string): Promise<Array<{ id: number; name: string; groupname: string; role: string; description: string | null; user_count: number }>> {
    return apiRequest(`/api/topics/${slug}/groups`);
}

// =============================================================================
// Article Publication Resources
// =============================================================================

export interface ArticlePublicationResources {
    article_id: number;
    resources: {
        popup_url: string | null;  // Parent ARTICLE resource with popup HTML (shown in navbar)
        html_url: string | null;   // HTML child resource (standalone HTML version)
        pdf_url: string | null;    // PDF child resource (downloadable PDF)
    };
    hash_ids: {
        popup: string | null;
        html: string | null;
        pdf: string | null;
    };
}

// Get publication resources for a published article
export async function getArticlePublicationResources(articleId: number): Promise<ArticlePublicationResources> {
    return apiRequest(`/api/content/article/${articleId}/resources`);
}

// Helper to get full URL for published article HTML
export function getPublishedArticleHtmlUrl(hashId: string): string {
    return `${PUBLIC_API_URL}/api/resources/content/${hashId}`;
}

// Helper to get full URL for published article PDF download
export function getPublishedArticlePdfUrl(hashId: string): string {
    return `${PUBLIC_API_URL}/api/resources/content/${hashId}`;
}
