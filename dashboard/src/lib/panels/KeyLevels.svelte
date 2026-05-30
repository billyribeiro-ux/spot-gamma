<script lang="ts">
	import AnimatedNumber from '$lib/AnimatedNumber.svelte';
	import type { GammaLevels } from '$lib/types';

	let { levels }: { levels: GammaLevels } = $props();

	// Colors match the price-chart overlays ($lib/levels) — Call Wall green,
	// Put Wall red (this used to be inverted).
	const rows = $derived(
		[
			{ label: 'Call Wall', value: levels.call_wall, color: 'var(--lvl-call)' },
			{ label: 'Hedge Wall', value: levels.hedge_wall, color: 'var(--lvl-hedge)' },
			{ label: 'Spot', value: levels.spot, color: 'var(--lvl-spot)' },
			{ label: 'Vol Trigger', value: levels.volatility_trigger, color: 'var(--lvl-vol)' },
			{ label: 'Gamma Flip', value: levels.zero_gamma, color: 'var(--lvl-flip)' },
			{ label: 'Abs Gamma', value: levels.absolute_gamma, color: 'var(--lvl-abs)' },
			{ label: 'Put Wall', value: levels.put_wall, color: 'var(--lvl-put)' }
		]
			.filter((r) => r.value != null)
			.sort((a, b) => (b.value ?? -Infinity) - (a.value ?? -Infinity))
	);

	const dist = (v: number | null) => (v == null ? null : ((v - levels.spot) / levels.spot) * 100);
</script>

<div class="panel card">
	<h2>Key Levels</h2>
	<ul>
		{#each rows as row (row.label)}
			{@const d = dist(row.value)}
			<li class:is-spot={row.label === 'Spot'} style:--c={row.color}>
				<span class="dot"></span>
				<span class="label">{row.label}</span>
				{#if row.label !== 'Spot' && d != null}
					<span class="dist" class:up={d >= 0} class:down={d < 0}>
						{d >= 0 ? '▲' : '▼'}{Math.abs(d).toFixed(2)}%
					</span>
				{/if}
				<AnimatedNumber
					class="value"
					value={row.value ?? 0}
					format={(n) => n.toLocaleString('en-US', { maximumFractionDigits: 2 })}
				/>
			</li>
		{/each}
	</ul>
</div>

<style>
	.card {
		padding: 1rem 1.2rem;
	}
	h2 {
		margin: 0 0 0.6rem;
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--text-lo);
		font-weight: 700;
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	li {
		display: grid;
		grid-template-columns: 10px 1fr auto auto;
		align-items: center;
		gap: 0.6rem;
		padding: 0.45rem 0.5rem;
		margin: 0 -0.5rem;
		border-radius: var(--r-sm);
		border-bottom: 1px solid var(--border);
		transition: background var(--dur-1);
	}
	li:last-child {
		border-bottom: none;
	}
	li:hover {
		background: var(--surface-2);
	}
	.dot {
		width: 9px;
		height: 9px;
		border-radius: 50%;
		background: var(--c);
		box-shadow: 0 0 8px color-mix(in oklab, var(--c) 60%, transparent);
	}
	.label {
		color: var(--text-mid);
		font-size: 0.92rem;
	}
	.dist {
		font-size: 0.7rem;
		font-variant-numeric: tabular-nums;
		color: var(--text-lo);
	}
	.dist.up {
		color: var(--up);
	}
	.dist.down {
		color: var(--down);
	}
	:global(.value) {
		font-weight: 700;
		color: var(--text-hi);
		font-size: 0.98rem;
	}
	.is-spot {
		background: var(--surface-2);
	}
	.is-spot .label {
		color: var(--text-hi);
		font-weight: 700;
	}
	.is-spot :global(.value) {
		color: var(--text-hi);
	}
</style>
