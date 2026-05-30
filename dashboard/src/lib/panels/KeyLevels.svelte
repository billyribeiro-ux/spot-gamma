<script lang="ts">
	import type { GammaLevels } from '$lib/types';
	import { formatLevel } from '$lib/api';

	let { levels }: { levels: GammaLevels } = $props();

	// Order top-to-bottom by price so the layout reads like a chart axis.
	const rows = $derived(
		[
			{ label: 'Call Wall', value: levels.call_wall, color: '#ef4444' },
			{ label: 'Spot', value: levels.spot, color: '#e5e7eb' },
			{ label: 'Volatility Trigger', value: levels.volatility_trigger, color: '#22d3ee' },
			{ label: 'Zero Gamma', value: levels.zero_gamma, color: '#eab308' },
			{ label: 'Put Wall', value: levels.put_wall, color: '#22c55e' }
		].sort((a, b) => (b.value ?? -Infinity) - (a.value ?? -Infinity))
	);
</script>

<div class="card">
	<h2>Key Levels</h2>
	<ul>
		{#each rows as row (row.label)}
			<li>
				<span class="dot" style:background={row.color}></span>
				<span class="label">{row.label}</span>
				<span class="value" class:spot={row.label === 'Spot'}>{formatLevel(row.value)}</span>
			</li>
		{/each}
	</ul>
</div>

<style>
	.card {
		background: #111827;
		border: 1px solid #1f2937;
		border-radius: 12px;
		padding: 1rem 1.25rem;
	}
	h2 {
		margin: 0 0 0.75rem;
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: #9ca3af;
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	li {
		display: grid;
		grid-template-columns: 14px 1fr auto;
		align-items: center;
		gap: 0.6rem;
		padding: 0.4rem 0;
		border-bottom: 1px solid #1f2937;
	}
	li:last-child {
		border-bottom: none;
	}
	.dot {
		width: 10px;
		height: 10px;
		border-radius: 50%;
	}
	.label {
		color: #d1d5db;
		font-size: 0.95rem;
	}
	.value {
		font-variant-numeric: tabular-nums;
		font-weight: 600;
		color: #f3f4f6;
	}
	.value.spot {
		color: #fff;
		background: #1f2937;
		padding: 0.1rem 0.5rem;
		border-radius: 6px;
	}
</style>
