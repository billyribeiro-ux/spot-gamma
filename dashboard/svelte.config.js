import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		// SPA: levels are fetched from the FastAPI backend at runtime, so there
		// is nothing to prerender. fallback enables client-side routing.
		adapter: adapter({ fallback: 'index.html' })
	}
};

export default config;
