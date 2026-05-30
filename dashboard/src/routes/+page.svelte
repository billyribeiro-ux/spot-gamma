<script lang="ts">
	import { fetchLevels } from '$lib/api';
	import { SYMBOLS, type GammaLevels, type Symbol } from '$lib/types';
	import RegimeBanner from '$lib/panels/RegimeBanner.svelte';
	import KeyLevels from '$lib/panels/KeyLevels.svelte';
	import GammaHeatmap from '$lib/panels/GammaHeatmap.svelte';
	import ExpiryTable from '$lib/panels/ExpiryTable.svelte';
	import ZeroDTE from '$lib/panels/ZeroDTE.svelte';
	import ThinkScriptExport from '$lib/panels/ThinkScriptExport.svelte';

	const REFRESH_MS = 30_000;

	let symbol = $state<Symbol>('SPX');
	let levels = $state<GammaLevels | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(false);
	let updatedAt = $state<string>('');

	async function load(sym: Symbol) {
		loading = true;
		error = null;
		try {
			levels = await fetchLevels(sym);
			updatedAt = new Date().toLocaleTimeString();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
			levels = null;
		} finally {
			loading = false;
		}
	}

	// Reload whenever the selected symbol changes, then poll on an interval.
	$effect(() => {
		load(symbol);
		const id = setInterval(() => load(symbol), REFRESH_MS);
		return () => clearInterval(id);
	});
</script>

<svelte:head><title>Spot Gamma — {symbol}</title></svelte:head>

<main>
	<header>
		<div>
			<h1>Spot Gamma Dashboard</h1>
			<p class="meta">
				Source of truth: Python gamma engine · refreshes every {REFRESH_MS / 1000}s
				{#if updatedAt}· updated {updatedAt}{/if}
			</p>
		</div>
		<nav>
			{#each SYMBOLS as s (s)}
				<button class:active={s === symbol} onclick={() => (symbol = s)}>{s}</button>
			{/each}
		</nav>
	</header>

	{#if error}
		<div class="error">
			<strong>Could not load {symbol}.</strong>
			{error}
			<div class="hint">Is the API running? <code>uvicorn api.main:app --port 8000</code></div>
		</div>
	{:else if !levels}
		<div class="placeholder">{loading ? 'Loading…' : 'No data.'}</div>
	{:else}
		<div class="spot-line">
			<span class="sym">{levels.symbol}</span>
			<span class="px">{levels.spot.toLocaleString()}</span>
		</div>
		<RegimeBanner {levels} />
		<div class="grid">
			<KeyLevels {levels} />
			<ZeroDTE {levels} />
			<ExpiryTable {levels} />
			<div class="wide"><GammaHeatmap {levels} /></div>
			<div class="wide"><ThinkScriptExport {levels} /></div>
		</div>
	{/if}
</main>

<style>
	:global(body) {
		margin: 0;
		background: #0b0f17;
		color: #e5e7eb;
		font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
	}
	main {
		max-width: 1100px;
		margin: 0 auto;
		padding: 1.5rem 1.25rem 3rem;
	}
	header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		flex-wrap: wrap;
		gap: 1rem;
		margin-bottom: 1.25rem;
	}
	h1 {
		margin: 0;
		font-size: 1.4rem;
	}
	.meta {
		margin: 0.25rem 0 0;
		color: #6b7280;
		font-size: 0.8rem;
	}
	nav {
		display: flex;
		gap: 0.4rem;
	}
	nav button {
		background: #111827;
		color: #9ca3af;
		border: 1px solid #1f2937;
		border-radius: 8px;
		padding: 0.4rem 0.9rem;
		font-weight: 600;
		cursor: pointer;
	}
	nav button.active {
		background: #2563eb;
		color: #fff;
		border-color: #2563eb;
	}
	.spot-line {
		display: flex;
		align-items: baseline;
		gap: 0.6rem;
		margin-bottom: 0.75rem;
	}
	.sym {
		color: #9ca3af;
		font-weight: 600;
	}
	.px {
		font-size: 1.8rem;
		font-weight: 700;
		font-variant-numeric: tabular-nums;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 1rem;
		margin-top: 1rem;
	}
	.wide {
		grid-column: 1 / -1;
	}
	.error {
		background: rgba(239, 68, 68, 0.1);
		border: 1px solid rgba(239, 68, 68, 0.4);
		border-radius: 12px;
		padding: 1rem 1.25rem;
		color: #fca5a5;
	}
	.hint {
		margin-top: 0.5rem;
		color: #9ca3af;
		font-size: 0.85rem;
	}
	.placeholder {
		color: #6b7280;
		padding: 2rem 0;
	}
	@media (max-width: 720px) {
		.grid {
			grid-template-columns: 1fr;
		}
	}
</style>
