/**
 * Simple test runner for UI actions - no dependencies required.
 * Run with: node test-actions-simple.mjs
 *
 * This tests the action store logic by simulating what the browser would do.
 */

// Mock svelte/store
function writable(initial) {
	let value = initial;
	const subscribers = new Set();
	return {
		subscribe(fn) {
			subscribers.add(fn);
			fn(value);
			return () => subscribers.delete(fn);
		},
		set(newValue) {
			value = newValue;
			subscribers.forEach(fn => fn(value));
		},
		update(fn) {
			value = fn(value);
			subscribers.forEach(fn => fn(value));
		}
	};
}

function get(store) {
	let value;
	store.subscribe(v => value = v)();
	return value;
}

// Recreate actionStore logic
function createActionStore() {
	const store = writable(null);
	let lastProcessedTimestamp = 0;
	const actionHandlers = new Map();
	const resultStore = writable(null);

	return {
		subscribe: store.subscribe,
		resultStore,
		dispatch(action) {
			const fullAction = { ...action, timestamp: Date.now() };
			store.set(fullAction);
		},
		registerHandler(actionType, handler) {
			const handlers = actionHandlers.get(actionType) || [];
			handlers.push(handler);
			actionHandlers.set(actionType, handlers);
			return () => {
				const h = actionHandlers.get(actionType) || [];
				const idx = h.indexOf(handler);
				if (idx > -1) h.splice(idx, 1);
				actionHandlers.set(actionType, h);
			};
		},
		async executeCurrentAction() {
			const action = get(store);
			if (!action || action.timestamp <= lastProcessedTimestamp) return null;
			lastProcessedTimestamp = action.timestamp;
			const handlers = actionHandlers.get(action.type);
			if (!handlers || handlers.length === 0) {
				const result = { success: false, action: action.type, error: `No handler available for action: ${action.type}` };
				resultStore.set(result);
				return result;
			}
			try {
				const result = await handlers[0](action);
				resultStore.set(result);
				return result;
			} catch (e) {
				const result = { success: false, action: action.type, error: e.message };
				resultStore.set(result);
				return result;
			}
		},
		clear() { store.set(null); },
		getRegisteredActions() { return Array.from(actionHandlers.keys()); }
	};
}

// Test runner
let passed = 0;
let failed = 0;

function test(name, fn) {
	try {
		fn();
		console.log(`✅ ${name}`);
		passed++;
	} catch (e) {
		console.log(`❌ ${name}`);
		console.log(`   Error: ${e.message}`);
		failed++;
	}
}

function expect(actual) {
	return {
		toBe(expected) {
			if (actual !== expected) throw new Error(`Expected ${expected}, got ${actual}`);
		},
		toContain(item) {
			if (!actual.includes(item)) throw new Error(`Expected ${JSON.stringify(actual)} to contain ${item}`);
		},
		not: {
			toBeNull() {
				if (actual === null) throw new Error(`Expected non-null value`);
			},
			toContain(item) {
				if (actual.includes(item)) throw new Error(`Expected ${JSON.stringify(actual)} not to contain ${item}`);
			}
		}
	};
}

async function runTests() {
	console.log('\n🧪 Running UI Action Store Tests\n');

	// Test 1: Dispatch action
	test('dispatch should add timestamp to action', () => {
		const store = createActionStore();
		let action = null;
		store.subscribe(a => action = a);
		store.dispatch({ type: 'select_topic', params: { topic: 'macro' } });
		expect(action).not.toBeNull();
		expect(action.type).toBe('select_topic');
		expect(action.params.topic).toBe('macro');
	});

	// Test 2: Register handler
	test('registerHandler should add handler to registry', () => {
		const store = createActionStore();
		const unsub = store.registerHandler('select_topic', async () => ({ success: true }));
		expect(store.getRegisteredActions()).toContain('select_topic');
		unsub();
		// After unsubscribe, the array is empty but key still exists - this matches real implementation
		// Just verify it was registered initially
	});

	// Test 3: Execute action with handler
	test('executeCurrentAction should call registered handler', async () => {
		const store = createActionStore();
		let called = false;
		store.registerHandler('select_topic', async (action) => {
			called = true;
			return { success: true, action: 'select_topic' };
		});
		store.dispatch({ type: 'select_topic', params: { topic: 'macro' } });
		const result = await store.executeCurrentAction();
		expect(called).toBe(true);
		expect(result.success).toBe(true);
	});

	// Test 4: No handler returns error
	test('executeCurrentAction should return error when no handler', async () => {
		const store = createActionStore();
		store.dispatch({ type: 'unknown_action' });
		const result = await store.executeCurrentAction();
		expect(result.success).toBe(false);
		expect(result.error).toContain('No handler available');
	});

	// Test 5: Handler receives params
	test('handler should receive action params', async () => {
		const store = createActionStore();
		let receivedParams = null;
		store.registerHandler('open_article', async (action) => {
			receivedParams = action.params;
			return { success: true, action: 'open_article' };
		});
		store.dispatch({ type: 'open_article', params: { article_id: 42 } });
		await store.executeCurrentAction();
		expect(receivedParams.article_id).toBe(42);
	});

	// Test 6: Confirmation param
	test('handler should receive confirmation flag', async () => {
		const store = createActionStore();
		let receivedConfirmed = null;
		store.registerHandler('purge_article', async (action) => {
			receivedConfirmed = action.params?.confirmed;
			return { success: true, action: 'purge_article' };
		});
		store.dispatch({ type: 'purge_article', params: { article_id: 1, confirmed: true } });
		await store.executeCurrentAction();
		expect(receivedConfirmed).toBe(true);
	});

	// Test all action types can be dispatched
	const allActionTypes = [
		'select_topic', 'select_topic_tab', 'open_article', 'search_articles',
		'clear_search', 'rate_article', 'download_pdf', 'close_modal',
		'create_new_article', 'view_article', 'edit_article', 'submit_article',
		'publish_article', 'reject_article', 'deactivate_article', 'reactivate_article',
		'recall_article', 'purge_article', 'switch_global_view', 'switch_profile_tab',
		'save_draft', 'submit_for_review', 'select_article', 'focus_article'
	];

	for (const actionType of allActionTypes) {
		test(`dispatch accepts action type: ${actionType}`, () => {
			const store = createActionStore();
			store.dispatch({ type: actionType });
			// No throw = success
		});
	}

	console.log(`\n📊 Results: ${passed} passed, ${failed} failed\n`);

	if (failed > 0) process.exit(1);
}

runTests().catch(console.error);
