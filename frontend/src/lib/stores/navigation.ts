import { writable, derived } from 'svelte/store';
import sectionsConfig from '../../../shared/sections.json';

// =============================================================================
// Types from Shared Configuration
// =============================================================================

// Extract section names from shared config
export type SectionName = keyof typeof sectionsConfig.sections;

// Section configuration type
export interface SectionConfig {
	name: string;
	route: string;
	required_role: string;
	requires_topic: boolean;
	requires_article: boolean;
	ui_actions: string[];
}

// Export sections config for use in other modules
export const SECTIONS: Record<SectionName, SectionConfig> = sectionsConfig.sections as Record<SectionName, SectionConfig>;

// =============================================================================
// Navigation Context
// =============================================================================

export interface NavigationContext {
	// Section name from shared config (e.g., 'reader_topic', 'analyst_dashboard')
	section: SectionName;
	// Topic slug (for sections with requires_topic=true)
	topic: string | null;
	// Article context (for sections with requires_article=true)
	articleId: number | null;
	articleHeadline: string | null;
	articleKeywords: string | null;
	articleStatus: string | null;  // draft, editor, published
	// Resource tracking
	resourceId: number | null;
	resourceName: string | null;
	resourceType: string | null;
	// View mode for pages with multiple views (e.g., editor/preview/resources)
	viewMode: string | null;
}

const defaultContext: NavigationContext = {
	section: 'home',
	topic: null,
	articleId: null,
	articleHeadline: null,
	articleKeywords: null,
	articleStatus: null,
	resourceId: null,
	resourceName: null,
	resourceType: null,
	viewMode: null
};

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Get section configuration by name
 */
export function getSectionConfig(section: SectionName): SectionConfig | undefined {
	return SECTIONS[section];
}

/**
 * Get available UI actions for a section (from shared config)
 */
export function getSectionActions(section: SectionName): string[] {
	const config = SECTIONS[section];
	return config?.ui_actions || [];
}

/**
 * Check if a section requires a topic parameter
 */
export function sectionRequiresTopic(section: SectionName): boolean {
	return SECTIONS[section]?.requires_topic ?? false;
}

/**
 * Check if a section requires an article parameter
 */
export function sectionRequiresArticle(section: SectionName): boolean {
	return SECTIONS[section]?.requires_article ?? false;
}

/**
 * Extract role from section name (e.g., 'analyst_dashboard' -> 'analyst')
 */
export function extractRoleFromSection(section: SectionName): string {
	const prefix = section.split('_')[0];
	const roleMap: Record<string, string> = {
		reader: 'reader',
		analyst: 'analyst',
		editor: 'editor',
		admin: 'admin',
		root: 'admin',
		user: 'reader',
		home: 'reader'
	};
	return roleMap[prefix] || 'reader';
}

/**
 * Build URL path from section and parameters
 */
export function buildSectionUrl(section: SectionName, topic?: string | null, articleId?: number | null): string {
	const config = SECTIONS[section];
	if (!config) return '/';

	let path = config.route;

	// Replace [topic] placeholder
	if (path.includes('[topic]')) {
		if (topic) {
			path = path.replace('[topic]', topic);
		} else {
			// If topic is required but not provided, return base path
			return path.split('/[topic]')[0] || '/';
		}
	}

	// Replace [id] placeholder
	if (path.includes('[id]')) {
		if (articleId) {
			path = path.replace('[id]', String(articleId));
		} else {
			// If article is required but not provided, return path without article
			return path.split('/article/[id]')[0].replace('/edit/[id]', '') || '/';
		}
	}

	return path;
}

// =============================================================================
// Navigation Store
// =============================================================================

function createNavigationStore() {
	const { subscribe, set, update } = writable<NavigationContext>(defaultContext);

	return {
		subscribe,
		set,
		update,

		/**
		 * Set the current section (from shared sections.json)
		 */
		setSection(section: SectionName) {
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
					return { ...ctx, articleId: null, articleHeadline: null, articleKeywords: null, articleStatus: null };
				} else {
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

// =============================================================================
// Derived Stores
// =============================================================================

/**
 * Derived store for agent label display
 */
export const agentLabel = derived(navigationContext, ($ctx) => {
	const topicDisplay = $ctx.topic
		? $ctx.topic.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
		: null;

	const sectionConfig = SECTIONS[$ctx.section];
	const sectionName = sectionConfig?.name || 'Chat';

	// Build contextual label based on section
	if ($ctx.section.startsWith('analyst')) {
		if ($ctx.articleId) {
			return `Content Agent: Editing Article #${$ctx.articleId}`;
		}
		return `Analyst Agent${topicDisplay ? `: ${topicDisplay}` : ''}`;
	}

	if ($ctx.section.startsWith('editor')) {
		if ($ctx.articleId) {
			return `Editor Agent: Reviewing Article #${$ctx.articleId}`;
		}
		return `Editor Agent${topicDisplay ? `: ${topicDisplay}` : ''}`;
	}

	if ($ctx.section.startsWith('admin') || $ctx.section.startsWith('root')) {
		return 'Admin Assistant';
	}

	if ($ctx.section === 'reader_search') {
		return 'Search Assistant';
	}

	if ($ctx.section.startsWith('user')) {
		return 'Profile Assistant';
	}

	return `Main Chat Agent${topicDisplay ? ` (${topicDisplay})` : ''}`;
});

/**
 * Derived store for navigation context display in chat panel.
 */
export interface NavigationDisplayInfo {
	role: string;           // Human-readable role
	roleClass: string;      // CSS class for styling
	topic: string | null;   // Human-readable topic
	path: string;           // Current URL path
	sectionName: string;    // Human-readable section name
}

export const navigationDisplayInfo = derived(navigationContext, ($ctx): NavigationDisplayInfo => {
	const role = extractRoleFromSection($ctx.section);
	const roleLabels: Record<string, string> = {
		reader: 'Reader',
		analyst: 'Analyst',
		editor: 'Editor',
		admin: 'Admin'
	};

	const topicDisplay = $ctx.topic
		? $ctx.topic.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
		: null;

	const sectionConfig = SECTIONS[$ctx.section];
	const path = buildSectionUrl($ctx.section, $ctx.topic, $ctx.articleId);

	return {
		role: roleLabels[role] || 'Reader',
		roleClass: role,
		topic: topicDisplay,
		path,
		sectionName: sectionConfig?.name || 'Home'
	};
});

// =============================================================================
// API Integration
// =============================================================================

/**
 * Get context for API requests (snake_case for backend)
 */
export function getNavigationContextForAPI(ctx: NavigationContext): {
	section: string;
	topic: string | null;
	article_id: number | null;
	article_headline: string | null;
	article_keywords: string | null;
	article_status: string | null;
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
		resource_id: ctx.resourceId,
		resource_name: ctx.resourceName,
		resource_type: ctx.resourceType,
		view_mode: ctx.viewMode
	};
}

// =============================================================================
// Editor Content Store
// =============================================================================

export interface LinkedResource {
	resource_id: number;
	name: string;
	type: string;
	hash_id?: string;
	already_linked?: boolean;
}

export type EditorContentAction = 'fill' | 'append' | 'replace' | 'update_headline' | 'update_keywords' | 'update_content';

export interface EditorContentPayload {
	headline?: string;
	content?: string;
	keywords?: string;
	action: EditorContentAction;
	linked_resources?: LinkedResource[];
	article_id?: number;
	timestamp: number;
}

function createEditorContentStore() {
	const { subscribe, set } = writable<EditorContentPayload | null>(null);

	return {
		subscribe,

		setContent(content: {
			headline?: string;
			content?: string;
			keywords?: string;
			action: string;
			linked_resources?: LinkedResource[];
			article_id?: number;
		}) {
			// Validate action type
			const validActions: EditorContentAction[] = ['fill', 'append', 'replace', 'update_headline', 'update_keywords', 'update_content'];
			const action = validActions.includes(content.action as EditorContentAction)
				? (content.action as EditorContentAction)
				: 'fill';

			set({
				headline: content.headline,
				content: content.content,
				keywords: content.keywords,
				action,
				linked_resources: content.linked_resources,
				article_id: content.article_id,
				timestamp: Date.now()
			});
		},

		clear() {
			set(null);
		}
	};
}

export const editorContentStore = createEditorContentStore();
