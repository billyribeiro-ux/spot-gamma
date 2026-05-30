import path from 'node:path';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { svelteTesting } from '@testing-library/svelte/vite';
import { defineConfig } from 'vitest/config';

// Pure-logic tests ($lib/levels, $lib/api) and component-render tests for
// jsdom-friendly components (e.g. the SVG GexProfile). Components that need
// WebGL/canvas (PriceChart, the Threlte scene) are covered by the live
// Playwright screenshots instead.
export default defineConfig({
	plugins: [svelte(), svelteTesting()],
	resolve: { alias: { $lib: path.resolve('./src/lib') } },
	test: {
		include: ['src/**/*.test.ts'],
		environment: 'jsdom'
	}
});
