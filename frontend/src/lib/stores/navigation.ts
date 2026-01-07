import { writable, derived } from 'svelte/store';

export type NavigationSection = 'home' | 'search' | 'analyst' | 'editor' | 'admin' | 'profile';
export type NavigationRole = 'reader' | 'analyst' | 'editor' | 'admin';

export interface NavigationContext {
	section: NavigationSection;
	topic: string | null;
	subNav: string | null;
	articleId: number | null;
	articleHeadline: string | null;
	articleKeywords: string | null;
	articleStatus: string | null;  // draft, editor, published
	role: NavigationRole;  // Current role based on navigation context
	// Resource tracking
	resourceId: number | null;
	resourceName: string | null;
	resourceType: string | null;
	// View mode for pages with multiple views
	viewMode: string | null;  // e.g., 'editor' | 'preview' | 'resources' for analyst edit
}

const defaultContext: NavigationContext = {
	section: 'home',
	topic: null,
	subNav: null,
	articleId: null,
	articleHeadline: null,
	articleKeywords: null,
	articleStatus: null,
	role: 'reader',  // Default role is reader
	resourceId: null,
	resourceName: null,
	resourceType: null,
	viewMode: null
};

function createNavigationStore() {
	const { subscribe, set, update } = writable<NavigationContext>(defaultContext);

	return {
		subscribe,
		set,
		update,

		/**
		 * Set the current navigation section
		 */
		setSection(section: NavigationSection) {
			update((ctx) => ({ ...ctx, section }));
		},

		/**
		 * Set the current topic
		 */
		setTopic(topic: string | null) {
			update((ctx) => ({ ...ctx, topic }));
		},

		/**
		 * Set the current article being viewed/edited
		 */
		setArticle(articleId: number | null, headline: string | null = null, keywords: string | null = null, status: string | null = null) {
			update((ctx) => ({ ...ctx, articleId, articleHeadline: headline, articleKeywords: keywords, articleStatus: status }));
		},

		/**
		 * Set the current resource being viewed
		 */
		setResource(resourceId: number | null, name: string | null = null, type: string | null = null) {
			update((ctx) => ({ ...ctx, resourceId, resourceName: name, resourceType: type }));
		},

		/**
		 * Set the current view mode (e.g., for article editor)
		 */
		setViewMode(viewMode: string | null) {
			update((ctx) => ({ ...ctx, viewMode }));
		},

		/**
		 * Toggle article selection - if same article, clear it; otherwise set it
		 */
		toggleArticle(articleId: number, headline: string | null = null, keywords: string | null = null, status: string | null = null) {
			update((ctx) => {
				if (ctx.articleId === articleId) {
					// Same article - clear it
					return { ...ctx, articleId: null, articleHeadline: null, articleKeywords: null, articleStatus: null };
				} else {
					// Different article - set it
					return { ...ctx, articleId, articleHeadline: headline, articleKeywords: keywords, articleStatus: status };
				}
			});
		},

		/**
		 * Clear article selection
		 */
		clearArticle() {
			update((ctx) => ({ ...ctx, articleId: null, articleHeadline: null, articleKeywords: null, articleStatus: null }));
		},

		/**
		 * Clear resource selection
		 */
		clearResource() {
			update((ctx) => ({ ...ctx, resourceId: null, resourceName: null, resourceType: null }));
		},

		/**
		 * Set sub-navigation (e.g., 'drafts', 'pending', 'latest')
		 */
		setSubNav(subNav: string | null) {
			update((ctx) => ({ ...ctx, subNav }));
		},

		/**
		 * Update multiple context properties at once
		 */
		setContext(partial: Partial<NavigationContext>) {
			update((ctx) => ({ ...ctx, ...partial }));
		},

		/**
		 * Reset to default context
		 */
		reset() {
			set(defaultContext);
		}
	};
}

export const navigationContext = createNavigationStore();

/**
 * Derived store for agent label display
 */
export const agentLabel = derived(navigationContext, ($ctx) => {
	const topicDisplay = $ctx.topic
		? $ctx.topic.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
		: null;

	switch ($ctx.section) {
		case 'analyst':
			if ($ctx.articleId) {
				return `Content Agent: Editing Article #${$ctx.articleId}`;
			}
			return `Analyst Agent${topicDisplay ? `: ${topicDisplay}` : ''}`;

		case 'editor':
			if ($ctx.articleId) {
				return `Editor Agent: Reviewing Article #${$ctx.articleId}`;
			}
			return `Editor Agent${topicDisplay ? `: ${topicDisplay}` : ''}`;

		case 'admin':
			return 'Admin Assistant';

		case 'search':
			return 'Search Assistant';

		case 'profile':
			return 'Profile Assistant';

		case 'home':
		default:
			return `Main Chat Agent${topicDisplay ? ` (${topicDisplay})` : ''}`;
	}
});

/**
 * Derived store for navigation context display in chat panel.
 * Shows role, topic, and navigation path.
 */
export interface NavigationDisplayInfo {
	role: string;           // Human-readable role
	roleClass: string;      // CSS class for styling
	topic: string | null;   // Human-readable topic
	path: string;           // Navigation path like /analyst/{topic}/edit/{id}
}

export const navigationDisplayInfo = derived(navigationContext, ($ctx): NavigationDisplayInfo => {
	// Format role for display
	const roleLabels: Record<NavigationRole, string> = {
		reader: 'Reader',
		analyst: 'Analyst',
		editor: 'Editor',
		admin: 'Admin'
	};

	// Format topic for display
	const topicDisplay = $ctx.topic
		? $ctx.topic.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
		: null;

	// Build navigation path
	let path = '/';
	switch ($ctx.section) {
		case 'home':
			path = $ctx.topic ? `/?tab=${$ctx.topic}` : '/';
			break;
		case 'search':
			path = '/?tab=search';
			break;
		case 'analyst':
			if ($ctx.articleId) {
				path = `/analyst/edit/${$ctx.articleId}`;
			} else if ($ctx.topic) {
				path = `/analyst/${$ctx.topic}`;
			} else {
				path = '/analyst';
			}
			break;
		case 'editor':
			if ($ctx.topic) {
				path = `/editor/${$ctx.topic}`;
			} else {
				path = '/editor';
			}
			break;
		case 'admin':
			path = $ctx.subNav ? `/admin/${$ctx.subNav}` : '/admin';
			break;
		case 'profile':
			path = $ctx.subNav ? `/profile?tab=${$ctx.subNav}` : '/profile';
			break;
	}

	return {
		role: roleLabels[$ctx.role],
		roleClass: $ctx.role,
		topic: topicDisplay,
		path
	};
});

/**
 * Get context for API requests
 */
export function getNavigationContextForAPI(ctx: NavigationContext): {
	section: string;
	topic: string | null;
	article_id: number | null;
	article_headline: string | null;
	article_keywords: string | null;
	article_status: string | null;
	sub_nav: string | null;
	role: string;
	resource_id: number | null;
	resource_name: string | null;
	resource_type: string | null;
	view_mode: string | null;
} {
	return {
		section: ctx.section,
		topic: ctx.topic,
		article_id: ctx.articleId,
		article_headline: ctx.articleHeadline,
		article_keywords: ctx.articleKeywords,
		article_status: ctx.articleStatus,
		sub_nav: ctx.subNav,
		role: ctx.role,
		resource_id: ctx.resourceId,
		resource_name: ctx.resourceName,
		resource_type: ctx.resourceType,
		view_mode: ctx.viewMode
	};
}

/**
 * Editor content store for passing generated content from chat to editor pages.
 * The chat agent can generate article content which should fill the editor fields.
 */
export interface LinkedResource {
	resource_id: number;
	name: string;
	type: string;
	hash_id?: string;
	already_linked?: boolean;
}

export interface EditorContentPayload {
	headline?: string;
	content?: string;
	keywords?: string;
	action: 'fill' | 'append' | 'replace';
	linked_resources?: LinkedResource[];
	article_id?: number;
	timestamp: number;  // To detect new content
}

function createEditorContentStore() {
	const { subscribe, set, update } = writable<EditorContentPayload | null>(null);

	return {
		subscribe,

		/**
		 * Set new editor content from chat response.
		 * The editor page will react to this and fill the fields.
		 */
		setContent(content: {
			headline?: string;
			content?: string;
			keywords?: string;
			action: string;
			linked_resources?: LinkedResource[];
			article_id?: number;
		}) {
			set({
				headline: content.headline,
				content: content.content,
				keywords: content.keywords,
				action: (content.action as 'fill' | 'append' | 'replace') || 'fill',
				linked_resources: content.linked_resources,
				article_id: content.article_id,
				timestamp: Date.now()
			});
		},

		/**
		 * Clear the content after it's been consumed by the editor.
		 */
		clear() {
			set(null);
		}
	};
}

export const editorContentStore = createEditorContentStore();
