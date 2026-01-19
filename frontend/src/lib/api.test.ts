import { describe, it, expect, beforeEach, vi, type Mock } from 'vitest';
import { searchArticles, type SearchParams } from './api';

// Mock the auth store
vi.mock('./stores/auth', () => ({
	auth: {
		subscribe: vi.fn((cb) => {
			cb({ accessToken: 'test-token', refreshToken: null, user: null, isAuthenticated: true });
			return () => {};
		})
	}
}));

// Mock global fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('searchArticles', () => {
	beforeEach(() => {
		mockFetch.mockReset();
		mockFetch.mockResolvedValue({
			ok: true,
			status: 200,
			json: () => Promise.resolve([])
		});
	});

	describe('topic parameter', () => {
		it('should search with "all" topic for cross-topic search', async () => {
			await searchArticles('all', { q: 'test' });

			expect(mockFetch).toHaveBeenCalledWith(
				'http://localhost:8000/api/reader/all/search?q=test',
				expect.objectContaining({
					headers: expect.any(Headers)
				})
			);
		});

		it('should search with specific topic', async () => {
			await searchArticles('macro', { q: 'inflation' });

			expect(mockFetch).toHaveBeenCalledWith(
				'http://localhost:8000/api/reader/macro/search?q=inflation',
				expect.any(Object)
			);
		});

		it('should search with topic containing special characters', async () => {
			await searchArticles('fixed-income', { q: 'bonds' });

			expect(mockFetch).toHaveBeenCalledWith(
				'http://localhost:8000/api/reader/fixed-income/search?q=bonds',
				expect.any(Object)
			);
		});
	});

	describe('query parameter (q)', () => {
		it('should include q parameter when provided', async () => {
			await searchArticles('equity', { q: 'stock market' });

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).toContain('q=stock+market');
		});

		it('should not include q parameter when empty', async () => {
			await searchArticles('macro', { q: '' });

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).not.toContain('q=');
		});

		it('should not include q parameter when undefined', async () => {
			await searchArticles('macro', {});

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).toBe('http://localhost:8000/api/reader/macro/search');
		});
	});

	describe('headline filter', () => {
		it('should include headline parameter', async () => {
			await searchArticles('all', { headline: 'Market Update' });

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).toContain('headline=Market+Update');
		});

		it('should not include headline when empty', async () => {
			await searchArticles('all', { headline: '' });

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).not.toContain('headline=');
		});
	});

	describe('keywords filter', () => {
		it('should include keywords parameter', async () => {
			await searchArticles('macro', { keywords: 'inflation,rates' });

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).toContain('keywords=inflation%2Crates');
		});

		it('should not include keywords when empty', async () => {
			await searchArticles('macro', { keywords: '' });

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).not.toContain('keywords=');
		});
	});

	describe('author filter', () => {
		it('should include author parameter', async () => {
			await searchArticles('equity', { author: 'John Doe' });

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).toContain('author=John+Doe');
		});

		it('should not include author when empty', async () => {
			await searchArticles('equity', { author: '' });

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).not.toContain('author=');
		});
	});

	describe('date range filters', () => {
		it('should include created_after parameter', async () => {
			await searchArticles('all', { created_after: '2024-01-01' });

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).toContain('created_after=2024-01-01');
		});

		it('should include created_before parameter', async () => {
			await searchArticles('all', { created_before: '2024-12-31' });

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).toContain('created_before=2024-12-31');
		});

		it('should include both date range parameters', async () => {
			await searchArticles('all', {
				created_after: '2024-01-01',
				created_before: '2024-06-30'
			});

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).toContain('created_after=2024-01-01');
			expect(url).toContain('created_before=2024-06-30');
		});

		it('should not include date filters when empty', async () => {
			await searchArticles('all', { created_after: '', created_before: '' });

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).not.toContain('created_after=');
			expect(url).not.toContain('created_before=');
		});
	});

	describe('limit parameter', () => {
		it('should include limit parameter', async () => {
			await searchArticles('macro', { limit: 25 });

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).toContain('limit=25');
		});

		it('should convert limit to string', async () => {
			await searchArticles('macro', { limit: 50 });

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).toContain('limit=50');
		});

		it('should not include limit when undefined', async () => {
			await searchArticles('macro', { q: 'test' });

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).not.toContain('limit=');
		});
	});

	describe('combined filters', () => {
		it('should combine multiple filters correctly', async () => {
			const params: SearchParams = {
				q: 'market',
				headline: 'Update',
				keywords: 'stocks',
				author: 'Jane',
				created_after: '2024-01-01',
				created_before: '2024-12-31',
				limit: 20
			};

			await searchArticles('all', params);

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).toContain('q=market');
			expect(url).toContain('headline=Update');
			expect(url).toContain('keywords=stocks');
			expect(url).toContain('author=Jane');
			expect(url).toContain('created_after=2024-01-01');
			expect(url).toContain('created_before=2024-12-31');
			expect(url).toContain('limit=20');
		});

		it('should only include non-empty parameters', async () => {
			const params: SearchParams = {
				q: 'market',
				headline: '',
				keywords: 'stocks',
				author: '',
				limit: 10
			};

			await searchArticles('equity', params);

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).toContain('q=market');
			expect(url).toContain('keywords=stocks');
			expect(url).toContain('limit=10');
			expect(url).not.toContain('headline=');
			expect(url).not.toContain('author=');
		});
	});

	describe('empty search', () => {
		it('should make request with no query params when all empty', async () => {
			await searchArticles('macro', {});

			expect(mockFetch).toHaveBeenCalledWith(
				'http://localhost:8000/api/reader/macro/search',
				expect.any(Object)
			);
		});

		it('should handle empty params object', async () => {
			await searchArticles('all', {});

			const url = (mockFetch as Mock).mock.calls[0][0] as string;
			expect(url).toBe('http://localhost:8000/api/reader/all/search');
		});
	});

	describe('authorization header', () => {
		it('should include Bearer token in request headers', async () => {
			await searchArticles('macro', { q: 'test' });

			const options = (mockFetch as Mock).mock.calls[0][1];
			const headers = options.headers as Headers;
			expect(headers.get('Authorization')).toBe('Bearer test-token');
		});

		it('should include Content-Type header', async () => {
			await searchArticles('macro', { q: 'test' });

			const options = (mockFetch as Mock).mock.calls[0][1];
			const headers = options.headers as Headers;
			expect(headers.get('Content-Type')).toBe('application/json');
		});
	});

	describe('error handling', () => {
		it('should throw on non-ok response', async () => {
			mockFetch.mockResolvedValue({
				ok: false,
				status: 400,
				json: () => Promise.resolve({ detail: 'Invalid topic: unknown' })
			});

			await expect(searchArticles('unknown', { q: 'test' })).rejects.toThrow();
		});

		it('should throw on network error', async () => {
			mockFetch.mockRejectedValue(new Error('Network error'));

			await expect(searchArticles('macro', { q: 'test' })).rejects.toThrow('Network error');
		});
	});

	describe('response handling', () => {
		it('should return parsed JSON response', async () => {
			const mockArticles = [
				{ id: 1, headline: 'Test Article', topic: 'macro' },
				{ id: 2, headline: 'Another Article', topic: 'equity' }
			];

			mockFetch.mockResolvedValue({
				ok: true,
				status: 200,
				json: () => Promise.resolve(mockArticles)
			});

			const result = await searchArticles('all', { q: 'article' });

			expect(result).toEqual(mockArticles);
		});

		it('should return empty array when no results', async () => {
			mockFetch.mockResolvedValue({
				ok: true,
				status: 200,
				json: () => Promise.resolve([])
			});

			const result = await searchArticles('macro', { q: 'nonexistent' });

			expect(result).toEqual([]);
		});
	});
});
