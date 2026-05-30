import { defineConfig, devices } from '@playwright/test';

// End-to-end smoke test. Playwright boots BOTH the FastAPI backend (sample
// source, so levels render with no external data) and the SvelteKit dev server
// (which proxies /api -> :8000), then drives a real browser. The price chart's
// candles come from a live source and are treated as best-effort; the assertions
// target the network-independent core (levels, panels, legend, navigation).
export default defineConfig({
	testDir: './e2e',
	timeout: 30_000,
	expect: { timeout: 10_000 },
	fullyParallel: true,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 1 : 0,
	reporter: process.env.CI ? 'github' : 'list',
	use: {
		baseURL: 'http://localhost:4173',
		trace: 'on-first-retry'
	},
	projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
	webServer: [
		{
			command: 'python3 -m uvicorn api.main:app --port 8000 --log-level warning',
			cwd: '..',
			url: 'http://localhost:8000/health',
			reuseExistingServer: !process.env.CI,
			timeout: 120_000,
			env: {
				PYTHONPATH: 'engine',
				SPOTGAMMA_SOURCE: 'sample',
				SPOTGAMMA_CONFIG: '/tmp/e2e-credentials.json'
			}
		},
		{
			command: 'npm run dev -- --port 4173 --strictPort',
			url: 'http://localhost:4173',
			reuseExistingServer: !process.env.CI,
			timeout: 120_000
		}
	]
});
