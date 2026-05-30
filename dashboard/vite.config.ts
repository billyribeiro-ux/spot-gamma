import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// Backend target + optional admin token are read from the environment so the
// token stays server-side (injected by the proxy) and is never shipped to the
// browser. Matches the API's SPOTGAMMA_ADMIN_TOKEN gate.
const API_TARGET = process.env.SPOTGAMMA_API_TARGET ?? 'http://localhost:8000';
const ADMIN_TOKEN = process.env.SPOTGAMMA_ADMIN_TOKEN;

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		port: 5173,
		// Proxy API calls to the FastAPI backend so the browser hits one origin.
		proxy: {
			'/api': {
				target: API_TARGET,
				changeOrigin: true,
				rewrite: (path) => path.replace(/^\/api/, ''),
				configure: (proxy) => {
					if (!ADMIN_TOKEN) return;
					proxy.on('proxyReq', (proxyReq: import('node:http').ClientRequest) => {
						proxyReq.setHeader('X-Admin-Token', ADMIN_TOKEN);
					});
				}
			}
		}
	}
});
