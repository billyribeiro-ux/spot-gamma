import { expect, test } from '@playwright/test';

test.describe('dashboard', () => {
	test('renders the gamma dashboard for the default symbol', async ({ page }) => {
		await page.goto('/');

		// Levels load from the offline sample source.
		await expect(page.locator('.spot-line')).toContainText('SPX', { timeout: 20_000 });

		// Regime banner + the SpotGamma level toggle legend (all 7 levels).
		await expect(page.locator('.legend .chip')).toHaveCount(7);

		// The d3 net-gamma-by-strike panel renders an SVG with bars.
		const byStrike = page.locator('section', { hasText: 'Net gamma by strike' });
		await expect(byStrike.locator('svg rect').first()).toBeVisible();

		// Key panels are present.
		await expect(page.getByText('Key Levels', { exact: false })).toBeVisible();
	});

	test('switches symbols via the nav', async ({ page }) => {
		await page.goto('/');
		await expect(page.locator('.spot-line')).toContainText('SPX', { timeout: 20_000 });
		await page.getByRole('button', { name: 'NDX', exact: true }).click();
		await expect(page.locator('.spot-line')).toContainText('NDX', { timeout: 20_000 });
	});

	test('toggling a level updates the legend state', async ({ page }) => {
		await page.goto('/');
		const putWall = page.locator('.chip', { hasText: 'Put Wall' });
		await expect(putWall).toBeVisible({ timeout: 20_000 });
		await expect(putWall).toHaveClass(/on/);
		await putWall.click();
		await expect(putWall).not.toHaveClass(/on/);
	});

	test('the connections hub lists sources', async ({ page }) => {
		await page.goto('/admin');
		await expect(page.getByRole('heading', { name: 'Connections' })).toBeVisible();
		// every source card (incl. the free cboe + sample) is shown
		await expect(page.locator('.card', { hasText: 'Cboe' })).toBeVisible({ timeout: 20_000 });
		await expect(page.locator('.card')).toHaveCount(7);
	});

	test('command palette opens, filters, and drives the symbol', async ({ page }) => {
		await page.goto('/');
		await expect(page.locator('.spot-line')).toContainText('SPX', { timeout: 20_000 });
		await page.keyboard.press('ControlOrMeta+k');
		const palette = page.getByRole('dialog', { name: 'Command palette' });
		await expect(palette).toBeVisible();
		await page.keyboard.type('NDX');
		await page.getByRole('option', { name: /View NDX/ }).click();
		await expect(palette).toBeHidden();
		await expect(page.locator('.spot-line')).toContainText('NDX', { timeout: 20_000 });
	});

	test('theme toggle switches to light and persists', async ({ page }) => {
		await page.goto('/');
		await expect(page.locator('.spot-line')).toBeVisible({ timeout: 20_000 });
		const root = page.locator('html');
		const start = await root.getAttribute('data-theme');
		await page.getByRole('button', { name: 'Toggle theme' }).click();
		await expect(root).not.toHaveAttribute('data-theme', start ?? 'dark');
		// persists across reload
		const after = await root.getAttribute('data-theme');
		await page.reload();
		await expect(root).toHaveAttribute('data-theme', after ?? 'light');
	});
});
