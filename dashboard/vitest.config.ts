import { defineConfig } from 'vitest/config';

// Unit tests cover the pure TS logic ($lib/levels, $lib/api formatters), which
// import only plain modules — no SvelteKit runtime — so a plain node env is enough.
export default defineConfig({
	test: {
		include: ['src/**/*.test.ts'],
		environment: 'node'
	}
});
