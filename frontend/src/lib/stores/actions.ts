import { writable, get } from 'svelte/store';

/**
 * UI Action types that can be triggered by the chatbot.
 * These correspond to button clicks, tab selections, and other UI interactions.
 */
export type UIActionType =
	// Analyst Edit Page Actions
	| 'save_draft'
	| 'submit_for_review'
	| 'switch_view_editor'
	| 'switch_view_preview'
	| 'switch_view_resources'
	// Resource Actions (for article editor)
	| 'add_resource'
	| 'remove_resource'
	| 'link_resource'
	| 'unlink_resource'
	| 'browse_resources'
	| 'open_resource_modal'
	// Analyst Hub Page Actions
	| 'create_new_article'
	| 'view_article'
	| 'edit_article'
	| 'submit_article'
	// Editor Hub Page Actions
	| 'reject_article'
	| 'publish_article'
	| 'download_pdf'
	// Admin Article Actions (require confirmation)
	| 'deactivate_article'
	| 'reactivate_article'
	| 'recall_article'
	| 'purge_article'
	| 'delete_article'
	| 'delete_resource'
	// Admin View Switching
	| 'switch_admin_view'
	| 'switch_admin_topic'
	| 'switch_admin_subview'
	// Profile Page Actions
	| 'switch_profile_tab'
	| 'save_tonality'
	| 'delete_account'
	// Home Page Actions
	| 'select_topic_tab'
	| 'rate_article'
	| 'open_article'
	| 'search_articles'
	| 'clear_search'
	// Common Actions
	| 'select_topic'
	| 'close_modal'
	| 'confirm_action'
	| 'cancel_action'
	// Context Update Actions (triggered by chat to request article/resource info)
	| 'select_article'
	| 'select_resource';

/**
 * UI Action payload sent from the chatbot.
 */
export interface UIAction {
	type: UIActionType;
	params?: {
		article_id?: number;
		topic?: string;
		rating?: number;
		search_query?: string;
		resource_id?: number;
		scope?: 'global' | 'topic' | 'article' | 'all';
		action?: 'add' | 'remove' | 'view';
		// Tab/view switching
		tab?: string;  // Tab name (e.g., 'info', 'settings' for profile)
		view?: string;  // View name (e.g., 'users', 'groups', 'prompts' for admin)
		subview?: string;  // Subview name (e.g., 'articles', 'resources' for topic view)
		// Confirmation
		requires_confirmation?: boolean;
		confirmation_message?: string;
		confirmed?: boolean;
		[key: string]: any;
	};
	timestamp: number;
}

/**
 * Action result reported back from UI components.
 */
export interface ActionResult {
	success: boolean;
	action: UIActionType;
	message?: string;
	error?: string;
	data?: any;
}

/**
 * Store for UI actions triggered by the chatbot.
 * Page components subscribe to this store and execute the corresponding actions.
 */
function createActionStore() {
	const { subscribe, set, update } = writable<UIAction | null>(null);

	// Keep track of the last processed action timestamp to avoid re-processing
	let lastProcessedTimestamp = 0;

	// Callbacks registered by page components
	const actionHandlers: Map<UIActionType, ((action: UIAction) => Promise<ActionResult>)[]> = new Map();

	// Results of executed actions (for chat to report back)
	const resultStore = writable<ActionResult | null>(null);

	return {
		subscribe,
		resultStore,

		/**
		 * Dispatch an action from the chatbot.
		 * The appropriate page component will handle it.
		 */
		dispatch(action: Omit<UIAction, 'timestamp'>) {
			const fullAction: UIAction = {
				...action,
				timestamp: Date.now()
			};
			console.log('🎯 Action dispatched:', fullAction);
			set(fullAction);
		},

		/**
		 * Register a handler for a specific action type.
		 * Called by page components when they mount.
		 */
		registerHandler(actionType: UIActionType, handler: (action: UIAction) => Promise<ActionResult>) {
			const handlers = actionHandlers.get(actionType) || [];
			handlers.push(handler);
			actionHandlers.set(actionType, handlers);
			console.log(`📝 Action handler registered for: ${actionType}`);

			// Return unsubscribe function
			return () => {
				const handlers = actionHandlers.get(actionType) || [];
				const index = handlers.indexOf(handler);
				if (index > -1) {
					handlers.splice(index, 1);
					if (handlers.length === 0) {
						actionHandlers.delete(actionType);
					} else {
						actionHandlers.set(actionType, handlers);
					}
					console.log(`📝 Action handler unregistered for: ${actionType}`);
				}
			};
		},

		/**
		 * Execute the current action using registered handlers.
		 * Returns the result of the action.
		 */
		async executeCurrentAction(): Promise<ActionResult | null> {
			const action = get({ subscribe });
			if (!action || action.timestamp <= lastProcessedTimestamp) {
				return null;
			}

			lastProcessedTimestamp = action.timestamp;

			const handlers = actionHandlers.get(action.type);
			if (!handlers || handlers.length === 0) {
				console.warn(`⚠️ No handler registered for action: ${action.type}`);
				const result: ActionResult = {
					success: false,
					action: action.type,
					error: `No handler available for action: ${action.type}`
				};
				resultStore.set(result);
				return result;
			}

			// Execute the first matching handler
			try {
				const result = await handlers[0](action);
				console.log(`✅ Action executed:`, result);
				resultStore.set(result);
				return result;
			} catch (e) {
				const result: ActionResult = {
					success: false,
					action: action.type,
					error: e instanceof Error ? e.message : 'Action execution failed'
				};
				console.error(`❌ Action failed:`, result);
				resultStore.set(result);
				return result;
			}
		},

		/**
		 * Clear the current action (after it's been processed).
		 */
		clear() {
			set(null);
		},

		/**
		 * Reset the store to initial state (for testing).
		 */
		reset() {
			set(null);
			lastProcessedTimestamp = 0;
			actionHandlers.clear();
		},

		/**
		 * Check if an action should be processed (not already processed).
		 */
		shouldProcess(action: UIAction | null): boolean {
			return action !== null && action.timestamp > lastProcessedTimestamp;
		},

		/**
		 * Mark an action as processed without executing it.
		 */
		markProcessed(action: UIAction) {
			if (action.timestamp > lastProcessedTimestamp) {
				lastProcessedTimestamp = action.timestamp;
			}
		},

		/**
		 * Get the list of registered action types.
		 */
		getRegisteredActions(): UIActionType[] {
			return Array.from(actionHandlers.keys());
		}
	};
}

export const actionStore = createActionStore();

// Expose actionStore on window for E2E testing
if (typeof window !== 'undefined') {
	(window as any).__actionStore = actionStore;
}

/**
 * Helper to create an action handler that wraps a simple async function.
 */
export function createActionHandler<T>(
	actionType: UIActionType,
	handler: (params: UIAction['params']) => Promise<T>
): (action: UIAction) => Promise<ActionResult> {
	return async (action: UIAction) => {
		try {
			const data = await handler(action.params);
			return {
				success: true,
				action: actionType,
				message: `${actionType} completed successfully`,
				data
			};
		} catch (e) {
			return {
				success: false,
				action: actionType,
				error: e instanceof Error ? e.message : 'Action failed'
			};
		}
	};
}
