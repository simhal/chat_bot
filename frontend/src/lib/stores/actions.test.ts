import { describe, it, expect, beforeEach, vi } from 'vitest';
import { actionStore, type UIAction, type ActionResult } from './actions';

describe('actionStore', () => {
	beforeEach(() => {
		// Reset the store between tests (clears handlers and processed timestamp)
		actionStore.reset();
	});

	describe('dispatch', () => {
		it('should dispatch an action with timestamp', () => {
			let dispatchedAction: UIAction | null = null;
			const unsubscribe = actionStore.subscribe((action) => {
				dispatchedAction = action;
			});

			actionStore.dispatch({ type: 'select_topic', params: { topic: 'macro' } });

			expect(dispatchedAction).not.toBeNull();
			expect(dispatchedAction?.type).toBe('select_topic');
			expect(dispatchedAction?.params?.topic).toBe('macro');
			expect(dispatchedAction?.timestamp).toBeGreaterThan(0);

			unsubscribe();
		});
	});

	describe('registerHandler', () => {
		it('should register a handler and return unsubscribe function', () => {
			const handler = vi.fn().mockResolvedValue({ success: true, action: 'select_topic' });
			const unsubscribe = actionStore.registerHandler('select_topic', handler);

			expect(actionStore.getRegisteredActions()).toContain('select_topic');

			unsubscribe();
			expect(actionStore.getRegisteredActions()).not.toContain('select_topic');
		});
	});

	describe('executeCurrentAction', () => {
		it('should execute registered handler when action is dispatched', async () => {
			const handler = vi.fn().mockResolvedValue({
				success: true,
				action: 'select_topic',
				message: 'Topic selected'
			});
			const unsubscribe = actionStore.registerHandler('select_topic', handler);

			actionStore.dispatch({ type: 'select_topic', params: { topic: 'macro' } });
			const result = await actionStore.executeCurrentAction();

			expect(handler).toHaveBeenCalled();
			expect(result?.success).toBe(true);
			expect(result?.action).toBe('select_topic');

			unsubscribe();
		});

		it('should return error when no handler is registered', async () => {
			actionStore.dispatch({ type: 'select_topic', params: { topic: 'macro' } });
			const result = await actionStore.executeCurrentAction();

			expect(result?.success).toBe(false);
			expect(result?.error).toContain('No handler available');
		});

		it('should not re-execute the same action twice', async () => {
			const handler = vi.fn().mockResolvedValue({ success: true, action: 'select_topic' });
			const unsubscribe = actionStore.registerHandler('select_topic', handler);

			actionStore.dispatch({ type: 'select_topic', params: { topic: 'macro' } });
			await actionStore.executeCurrentAction();
			await actionStore.executeCurrentAction();

			expect(handler).toHaveBeenCalledTimes(1);

			unsubscribe();
		});

		it('should handle handler errors gracefully', async () => {
			const handler = vi.fn().mockRejectedValue(new Error('Handler failed'));
			const unsubscribe = actionStore.registerHandler('select_topic', handler);

			actionStore.dispatch({ type: 'select_topic', params: { topic: 'macro' } });
			const result = await actionStore.executeCurrentAction();

			expect(result?.success).toBe(false);
			expect(result?.error).toBe('Handler failed');

			unsubscribe();
		});
	});

	describe('shouldProcess', () => {
		it('should return true for new actions', () => {
			actionStore.dispatch({ type: 'select_topic', params: { topic: 'macro' } });
			let action: UIAction | null = null;
			const unsubscribe = actionStore.subscribe((a) => {
				action = a;
			});

			expect(actionStore.shouldProcess(action)).toBe(true);

			unsubscribe();
		});

		it('should return false for already processed actions', async () => {
			const handler = vi.fn().mockResolvedValue({ success: true, action: 'select_topic' });
			const unsubscribe = actionStore.registerHandler('select_topic', handler);

			actionStore.dispatch({ type: 'select_topic', params: { topic: 'macro' } });
			await actionStore.executeCurrentAction();

			let action: UIAction | null = null;
			const unsub2 = actionStore.subscribe((a) => {
				action = a;
			});

			expect(actionStore.shouldProcess(action)).toBe(false);

			unsubscribe();
			unsub2();
		});
	});
});

// Test action type definitions
describe('UI Action Types', () => {
	beforeEach(() => {
		actionStore.reset();
	});

	const allActionTypes = [
		// Analyst Edit Page
		'save_draft',
		'submit_for_review',
		'switch_view_editor',
		'switch_view_preview',
		'switch_view_resources',
		// Resource Actions
		'add_resource',
		'remove_resource',
		'link_resource',
		'unlink_resource',
		'browse_resources',
		'open_resource_modal',
		// Analyst Hub
		'create_new_article',
		'view_article',
		'edit_article',
		'submit_article',
		// Editor Hub
		'reject_article',
		'publish_article',
		'download_pdf',
		// Admin Actions
		'deactivate_article',
		'reactivate_article',
		'recall_article',
		'purge_article',
		'delete_article',
		'delete_resource',
		// Admin View Switching
		'switch_admin_view',
		'switch_admin_topic',
		'switch_admin_subview',
		// Profile
		'switch_profile_tab',
		'save_tonality',
		'delete_account',
		// Home Page
		'select_topic_tab',
		'rate_article',
		'open_article',
		'search_articles',
		'clear_search',
		// Common
		'select_topic',
		'close_modal',
		'confirm_action',
		'cancel_action',
		'select_article',
		'select_resource'
	];

	it.each(allActionTypes)('should accept action type: %s', (actionType) => {
		// This test validates that all expected action types can be dispatched
		expect(() => {
			actionStore.dispatch({ type: actionType as any });
		}).not.toThrow();
	});
});

// Test action parameters
describe('Action Parameters', () => {
	beforeEach(() => {
		actionStore.reset();
	});

	it('should pass article_id to handler', async () => {
		let receivedParams: any = null;
		const handler = vi.fn().mockImplementation((action: UIAction) => {
			receivedParams = action.params;
			return Promise.resolve({ success: true, action: 'open_article' });
		});
		const unsubscribe = actionStore.registerHandler('open_article', handler);

		actionStore.dispatch({ type: 'open_article', params: { article_id: 42 } });
		await actionStore.executeCurrentAction();

		expect(receivedParams?.article_id).toBe(42);
		unsubscribe();
	});

	it('should pass topic to handler', async () => {
		let receivedParams: any = null;
		const handler = vi.fn().mockImplementation((action: UIAction) => {
			receivedParams = action.params;
			return Promise.resolve({ success: true, action: 'select_topic' });
		});
		const unsubscribe = actionStore.registerHandler('select_topic', handler);

		actionStore.dispatch({ type: 'select_topic', params: { topic: 'equity' } });
		await actionStore.executeCurrentAction();

		expect(receivedParams?.topic).toBe('equity');
		unsubscribe();
	});

	it('should pass confirmation flag to handler', async () => {
		let receivedParams: any = null;
		const handler = vi.fn().mockImplementation((action: UIAction) => {
			receivedParams = action.params;
			return Promise.resolve({ success: true, action: 'purge_article' });
		});
		const unsubscribe = actionStore.registerHandler('purge_article', handler);

		actionStore.dispatch({
			type: 'purge_article',
			params: { article_id: 123, confirmed: true }
		});
		await actionStore.executeCurrentAction();

		expect(receivedParams?.article_id).toBe(123);
		expect(receivedParams?.confirmed).toBe(true);
		unsubscribe();
	});
});
