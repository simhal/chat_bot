import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
	test: {
		include: ['src/**/*.{test,spec}.{js,ts}'],
		environment: 'jsdom',
		globals: true,
		setupFiles: ['./src/test-setup.ts']
	},
	resolve: {
		conditions: ['browser'],
		alias: {
			'$env/static/public': path.resolve(__dirname, './src/test-mocks/env.ts'),
			'$lib': path.resolve(__dirname, './src/lib')
		}
	}
});
