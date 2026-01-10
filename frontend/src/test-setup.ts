// Test setup for Vitest
import { vi } from 'vitest';

// Mock browser environment
vi.mock('$app/environment', () => ({
	browser: true,
	dev: true,
	building: false
}));

vi.mock('$app/navigation', () => ({
	goto: vi.fn(),
	invalidate: vi.fn(),
	invalidateAll: vi.fn(),
	preloadData: vi.fn(),
	preloadCode: vi.fn(),
	beforeNavigate: vi.fn(),
	afterNavigate: vi.fn()
}));

vi.mock('$app/stores', () => ({
	page: {
		subscribe: vi.fn((cb) => {
			cb({
				url: new URL('http://localhost:3000'),
				params: {},
				route: { id: '/' },
				status: 200,
				error: null,
				data: {},
				form: null
			});
			return () => {};
		})
	},
	navigating: {
		subscribe: vi.fn((cb) => {
			cb(null);
			return () => {};
		})
	},
	updated: {
		subscribe: vi.fn((cb) => {
			cb(false);
			return () => {};
		}),
		check: vi.fn()
	}
}));
