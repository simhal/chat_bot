import { writable, get } from 'svelte/store';
import uiActionsConfig from '../../../shared/ui_actions.json';
import type { SectionName } from './navigation';

// =============================================================================
// Types from Shared Configuration
// =============================================================================

// Global action names from config
type GlobalActionName = typeof uiActionsConfig.global_actions[number]['action'];

// Section action names from config
type SectionActionName = keyof typeof uiActionsConfig.section_actions;

// Combined UI action type - includes global actions and section-specific actions
// Note: Explicitly include 'goto_back' to ensure type inference works correctly
export type UIActionType = GlobalActionName | SectionActionName | 'goto_back';

// Action parameter types
export interface ActionParams {
	// Navigation (for 'goto' action)
	section?: SectionName;
	topic?: string;
	article_id?: number;
	// Article operations
	rating?: number;
	search_query?: string;
	feedback?: string;
	// Resource operations
	resource_id?: number;
	scope?: 'global' | 'topic' | 'article' | 'all';
	// User/group operations
	user_id?: number;
	group_id?: number;
	// Topic operations
	topic_id?: number;
	topic_ids?: number[];
	// Tonality operations
	tonality_id?: number;
	chat_tonality_id?: number;
	content_tonality_id?: number;
	// Prompt operations
	prompt_id?: number;
	// Confirmation
	requires_confirmation?: boolean;
	confirmation_message?: string;
	confirmed?: boolean;
	// Generic
	[key: string]: any;
}

/**
 * UI Action payload sent from the chatbot.
 */
export interface UIAction {
	type: UIActionType;
	params?: ActionParams;
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

// =============================================================================
// Action Configuration Helpers
// =============================================================================

/**
 * Get configuration for a global action
 */
export function getGlobalActionConfig(actionName: string) {
	return uiActionsConfig.global_actions.find(a => a.action === actionName);
}

/**
 * Get configuration for a section action
 */
export function getSectionActionConfig(actionName: string) {
	return (uiActionsConfig.section_actions as Record<string, any>)[actionName];
}

/**
 * Check if an action is a global action
 */
export function isGlobalAction(actionName: string): boolean {
	return uiActionsConfig.global_actions.some(a => a.action === actionName);
}

/**
 * Get all global action names
 */
export function getGlobalActionNames(): string[] {
	return uiActionsConfig.global_actions.map(a => a.action);
}

// =============================================================================
// Action Store
// =============================================================================

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
