<script lang="ts">
	import { goto } from '$app/navigation';
	import { fly } from 'svelte/transition';
	import { expoOut } from 'svelte/easing';
	import { fetchLevels, formatGex } from '$lib/api';
	import { SYMBOLS, TIMEFRAMES, type GammaLevels, type Symbol, type Timeframe } from '$lib/types';
	import { motionOK, stagger } from '$lib/motion';
	import { theme } from '$lib/theme.svelte';
	import AnimatedNumber from '$lib/AnimatedNumber.svelte';
	import CommandPalette, { type Command } from '$lib/CommandPalette.svelte';
	import RegimeBanner from '$lib/panels/RegimeBanner.svelte';
	import KeyLevels from '$lib/panels/KeyLevels.svelte';
	import PriceChart from '$lib/panels/PriceChart.svelte';
	import GammaTerrain from '$lib/panels/GammaTerrain.svelte';
	import GammaByStrike from '$lib/panels/GammaByStrike.svelte';
	import ExpiryTable from '$lib/panels/ExpiryTable.svelte';
	import ZeroDTE from '$lib/panels/ZeroDTE.svelte';
	import ThinkScriptExport from '$lib/panels/ThinkScriptExport.svelte';

	const REFRESH_MS = 30_000;

	let symbol = $state<Symbol>('SPX');
	let timeframe = $state<Timeframe>('5m');
	let levels = $state<GammaLevels | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(false);
	let updatedAt = $state<string>('');
	let cmdkOpen = $state(false);

	const activeIndex = $derived(SYMBOLS.indexOf(symbol));
	const D = motionOK() ? 1 : 0;
	const enter = (i: number) => ({ y: 14, opacity: 0, duration: 460 * D, delay: stagger(i) * D, easing: expoOut });

	// Command palette (⌘K): symbols, timeframes, theme, navigation.
	const commands = $derived<Command[]>([
		...SYMBOLS.map((s) => ({
			id: `sym-${s}`,
			label: `View ${s}`,
			group: 'Symbols',
			hint: s === symbol ? 'current' : '',
			keywords: 'symbol ticker',
			run: () => (symbol = s)
		})),
		...TIMEFRAMES.map((tf) => ({
			id: `tf-${tf}`,
			label: `Timeframe ${tf}`,
			group: 'Timeframe',
			hint: tf === timeframe ? 'current' : '',
			keywords: 'interval chart',
			run: () => (timeframe = tf)
		})),
		{
			id: 'theme',
			label: theme.current === 'dark' ? 'Switch to light theme' : 'Switch to dark theme',
			group: 'Appearance',
			keywords: 'dark light mode color',
			run: () => theme.toggle()
		},
		{ id: 'nav-conn', label: 'Open Connections', group: 'Navigate', keywords: 'sources api admin', run: () => goto('/admin') }
	]);

	async function load(sym: Symbol) {
		loading = true;
		error = null;
		try {
			levels = await fetchLevels(sym);
			updatedAt = new Date().toLocaleTimeString('en-US');
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

<header class="appbar">
	<a class="brand" href="/">
		<span class="mark">Γ</span>
		<span class="word">SPOT<b>GAMMA</b></span>
	</a>

	<nav class="seg" style="--n: {SYMBOLS.length}; --i: {activeIndex}" aria-label="Symbol">
		<span class="seg-ind" aria-hidden="true"></span>
		{#each SYMBOLS as s (s)}
			<button class:active={s === symbol} aria-pressed={s === symbol} onclick={() => (symbol = s)}>{s}</button>
		{/each}
	</nav>

	<div class="status">
		<span class="live" class:on={!error}><i></i>{error ? 'OFFLINE' : 'LIVE'}</span>
		{#if updatedAt}<span class="updated mono">{updatedAt}</span>{/if}
		<button class="icon-btn" onclick={() => theme.toggle()} aria-label="Toggle theme" title="Toggle theme">
			{#if theme.current === 'dark'}
				<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.5" /><g class="rays"><line x1="12" y1="2" x2="12" y2="5" /><line x1="12" y1="19" x2="12" y2="22" /><line x1="2" y1="12" x2="5" y2="12" /><line x1="19" y1="12" x2="22" y2="12" /><line x1="4.9" y1="4.9" x2="7" y2="7" /><line x1="17" y1="17" x2="19.1" y2="19.1" /><line x1="4.9" y1="19.1" x2="7" y2="17" /><line x1="17" y1="7" x2="19.1" y2="4.9" /></g></svg>
			{:else}
				<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>
			{/if}
		</button>
		<button class="cmdk" onclick={() => (cmdkOpen = true)} aria-label="Open command palette">
			<span class="mono">⌘K</span>
		</button>
		<a class="conn" href="/admin">Connections</a>
	</div>
</header>

<CommandPalette bind:open={cmdkOpen} {commands} />

<main>
	{#if error}
		<div class="error" in:fly={enter(0)}>
			<strong>Couldn't load {symbol}.</strong>
			{error}
			<div class="hint">Is the API running? <code>uvicorn api.main:app --port 8000</code></div>
		</div>
	{:else if !levels}
		<div class="skeletons">
			<div class="sk sk-hero"></div>
			<div class="sk sk-banner"></div>
			<div class="sk sk-wide"></div>
			<div class="sk sk-wide"></div>
		</div>
	{:else}
		<div class="hero" in:fly={enter(0)}>
			<div class="spot-line">
				<span class="sym">{levels.symbol}</span>
				<AnimatedNumber
					class="px mono"
					flash
					value={levels.spot}
					format={(n) => n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
				/>
			</div>
			<div class="hero-side">
				<span class="gex-chip {levels.regime}">
					<span class="gex-dot"></span>
					NET GEX {formatGex(levels.net_gex)}
				</span>
				<span class="asof">delayed · {updatedAt}</span>
			</div>
		</div>

		<div in:fly={enter(1)}><RegimeBanner {levels} /></div>
		<div class="grid">
			<div class="wide" in:fly={enter(2)}><PriceChart {symbol} {levels} bind:timeframe /></div>
			<div class="wide" in:fly={enter(3)}><GammaTerrain {levels} /></div>
			<div class="wide" in:fly={enter(4)}><GammaByStrike {levels} /></div>
			<div in:fly={enter(5)}><KeyLevels {levels} /></div>
			<div in:fly={enter(6)}><ZeroDTE {levels} /></div>
			<div in:fly={enter(7)}><ExpiryTable {levels} /></div>
			<div class="wide" in:fly={enter(8)}><ThinkScriptExport {symbol} {levels} /></div>
		</div>
	{/if}
</main>

<style>
	.appbar {
		position: sticky;
		top: 0;
		z-index: 50;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.7rem max(1.25rem, calc((100% - 1180px) / 2));
		background: color-mix(in oklab, var(--bg-0) 78%, transparent);
		backdrop-filter: blur(14px) saturate(140%);
		border-bottom: 1px solid var(--border);
	}
	.brand {
		display: inline-flex;
		align-items: center;
		gap: 0.55rem;
		text-decoration: none;
		color: var(--text-hi);
	}
	.brand .mark {
		display: grid;
		place-items: center;
		width: 28px;
		height: 28px;
		border-radius: 8px;
		font-weight: 800;
		font-size: 1.05rem;
		color: var(--bg-0);
		background: linear-gradient(145deg, var(--gold), #b8862b);
		box-shadow: 0 2px 10px -2px rgba(227, 179, 65, 0.5);
	}
	.brand .word {
		font-weight: 600;
		letter-spacing: 0.12em;
		font-size: 0.82rem;
		color: var(--text-mid);
	}
	.brand .word b {
		color: var(--text-hi);
		font-weight: 800;
	}

	/* segmented control with a sliding active pill */
	.seg {
		position: relative;
		display: grid;
		grid-auto-flow: column;
		grid-auto-columns: 1fr;
		gap: 2px;
		padding: 3px;
		background: var(--surface-1);
		border: 1px solid var(--border);
		border-radius: var(--r-pill);
	}
	.seg-ind {
		position: absolute;
		top: 3px;
		bottom: 3px;
		left: 3px;
		width: calc((100% - 6px) / var(--n));
		transform: translateX(calc(var(--i) * 100%));
		background: var(--accent);
		border-radius: var(--r-pill);
		box-shadow: 0 2px 12px -2px var(--accent);
		transition: transform var(--dur-2) var(--ease-out);
	}
	.seg button {
		position: relative;
		z-index: 1;
		background: none;
		border: none;
		color: var(--text-mid);
		font: inherit;
		font-weight: 700;
		font-size: 0.8rem;
		letter-spacing: 0.03em;
		padding: 0.35rem 0.95rem;
		cursor: pointer;
		transition: color var(--dur-1);
	}
	.seg button.active {
		color: #fff;
	}
	.seg button:not(.active):hover {
		color: var(--text-hi);
	}

	.status {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		font-size: 0.78rem;
	}
	.live {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		color: var(--text-lo);
		font-weight: 700;
		letter-spacing: 0.08em;
		font-size: 0.68rem;
	}
	.live i {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: var(--text-lo);
	}
	.live.on {
		color: var(--up);
	}
	.live.on i {
		background: var(--up);
		box-shadow: 0 0 0 0 rgba(46, 211, 144, 0.6);
		animation: pulse 2.4s ease-out infinite;
	}
	@keyframes pulse {
		0% {
			box-shadow: 0 0 0 0 rgba(46, 211, 144, 0.55);
		}
		70% {
			box-shadow: 0 0 0 7px rgba(46, 211, 144, 0);
		}
		100% {
			box-shadow: 0 0 0 0 rgba(46, 211, 144, 0);
		}
	}
	.updated {
		color: var(--text-lo);
	}
	.icon-btn {
		display: grid;
		place-items: center;
		width: 30px;
		height: 30px;
		padding: 0;
		color: var(--text-mid);
		background: none;
		border: 1px solid var(--border);
		border-radius: var(--r-pill);
		cursor: pointer;
		transition:
			color var(--dur-1),
			border-color var(--dur-1),
			background var(--dur-1);
	}
	.icon-btn svg {
		width: 16px;
		height: 16px;
		fill: none;
		stroke: currentColor;
		stroke-width: 2;
		stroke-linecap: round;
	}
	.icon-btn:hover {
		color: var(--text-hi);
		border-color: var(--border-strong);
		background: var(--surface-2);
	}
	.cmdk {
		display: inline-flex;
		align-items: center;
		color: var(--text-lo);
		background: var(--surface-1);
		border: 1px solid var(--border);
		border-radius: var(--r-sm);
		padding: 0.25rem 0.5rem;
		font-size: 0.7rem;
		cursor: pointer;
		transition:
			color var(--dur-1),
			border-color var(--dur-1),
			background var(--dur-1);
	}
	.cmdk:hover {
		color: var(--text-hi);
		border-color: var(--border-strong);
		background: var(--surface-2);
	}
	.conn {
		color: var(--text-mid);
		text-decoration: none;
		font-weight: 600;
		padding: 0.3rem 0.7rem;
		border: 1px solid var(--border);
		border-radius: var(--r-pill);
		transition:
			border-color var(--dur-1),
			color var(--dur-1),
			background var(--dur-1);
	}
	.conn:hover {
		color: var(--text-hi);
		border-color: var(--border-strong);
		background: var(--surface-2);
	}
	.appbar,
	.seg,
	.seg button {
		transition: var(--theme-tx);
	}

	main {
		max-width: 1180px;
		margin: 0 auto;
		padding: 1.5rem 1.25rem 4rem;
	}

	.hero {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
		margin-bottom: 1.1rem;
	}
	.spot-line {
		display: flex;
		align-items: baseline;
		gap: 0.7rem;
	}
	.sym {
		color: var(--text-lo);
		font-weight: 700;
		letter-spacing: 0.05em;
		font-size: 1rem;
	}
	:global(.px) {
		font-size: clamp(2.2rem, 5vw, 3.1rem);
		font-weight: 700;
		line-height: 1;
		letter-spacing: -0.02em;
		color: var(--text-hi);
	}
	.hero-side {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 0.3rem;
	}
	.gex-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.45rem;
		font-size: 0.78rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		padding: 0.3rem 0.7rem;
		border-radius: var(--r-pill);
		border: 1px solid var(--border);
	}
	.gex-chip .gex-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
	}
	.gex-chip.positive {
		color: var(--up);
		background: var(--up-dim);
		border-color: color-mix(in oklab, var(--up) 40%, transparent);
	}
	.gex-chip.positive .gex-dot {
		background: var(--up);
	}
	.gex-chip.negative {
		color: var(--down);
		background: var(--down-dim);
		border-color: color-mix(in oklab, var(--down) 40%, transparent);
	}
	.gex-chip.negative .gex-dot {
		background: var(--down);
	}
	.asof {
		color: var(--text-lo);
		font-size: 0.72rem;
	}

	.grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 1rem;
		margin-top: 1rem;
	}
	.wide {
		grid-column: 1 / -1;
	}

	/* skeleton loading */
	.skeletons {
		display: grid;
		gap: 1rem;
		margin-top: 0.5rem;
	}
	.sk {
		border-radius: var(--r-md);
		background:
			linear-gradient(100deg, transparent 20%, rgba(255, 255, 255, 0.05) 40%, transparent 60%),
			var(--surface-1);
		background-size:
			200% 100%,
			auto;
		border: 1px solid var(--border);
		animation: shimmer 1.4s linear infinite;
	}
	.sk-hero {
		height: 64px;
		width: 40%;
	}
	.sk-banner {
		height: 78px;
	}
	.sk-wide {
		height: 320px;
	}
	@keyframes shimmer {
		to {
			background-position:
				-200% 0,
				0 0;
		}
	}

	.error {
		background: var(--down-dim);
		border: 1px solid color-mix(in oklab, var(--down) 45%, transparent);
		border-radius: var(--r-md);
		padding: 1rem 1.25rem;
		color: #ffd2d8;
	}
	.hint {
		margin-top: 0.5rem;
		color: var(--text-mid);
		font-size: 0.85rem;
	}
	.hint code {
		font-family: var(--font-mono);
		background: var(--surface-2);
		padding: 0.1rem 0.4rem;
		border-radius: 6px;
	}

	@media (max-width: 760px) {
		.grid {
			grid-template-columns: 1fr;
		}
		.appbar {
			flex-wrap: wrap;
		}
	}
</style>
