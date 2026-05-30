<script lang="ts">
	import { formatGex } from '$lib/api';
	import AnimatedNumber from '$lib/AnimatedNumber.svelte';
	import type { GammaLevels } from '$lib/types';

	let { levels }: { levels: GammaLevels } = $props();
	const pct = $derived(Math.round(levels.zero_dte_share * 100));
	const positive = $derived(levels.zero_dte_net_gex >= 0);
</script>

<div class="panel card">
	<h2>0DTE Concentration</h2>
	<div class="readout">
		<AnimatedNumber class="big" value={pct} format={(n) => `${Math.round(n)}`} />
		<span class="pct">%</span>
	</div>
	<div class="sub">of total |gamma| expires today</div>

	<div class="meter"><span style:width="{pct}%"></span></div>

	<div class="net" class:pos={positive} class:neg={!positive}>
		<span class="net-label">0DTE NET GEX</span>
		<span class="net-val">{formatGex(levels.zero_dte_net_gex)}</span>
	</div>
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
	.readout {
		display: flex;
		align-items: baseline;
		gap: 0.1rem;
	}
	:global(.big) {
		font-size: 2.6rem;
		font-weight: 800;
		line-height: 1;
		letter-spacing: -0.02em;
		color: var(--text-hi);
	}
	.pct {
		font-size: 1.3rem;
		font-weight: 700;
		color: var(--text-lo);
	}
	.sub {
		color: var(--text-mid);
		font-size: 0.82rem;
		margin-top: 0.3rem;
	}
	.meter {
		margin-top: 0.85rem;
		height: 8px;
		background: var(--surface-2);
		border-radius: var(--r-pill);
		overflow: hidden;
	}
	.meter span {
		display: block;
		height: 100%;
		border-radius: var(--r-pill);
		background: linear-gradient(90deg, var(--accent), var(--lvl-abs));
		box-shadow: 0 0 12px -2px var(--accent);
		transition: width var(--dur-3) var(--ease-out);
	}
	.net {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		margin-top: 0.85rem;
		padding-top: 0.7rem;
		border-top: 1px solid var(--border);
	}
	.net-label {
		font-size: 0.66rem;
		letter-spacing: 0.08em;
		color: var(--text-lo);
	}
	.net-val {
		font-variant-numeric: tabular-nums;
		font-weight: 700;
		font-size: 0.95rem;
	}
	.pos .net-val {
		color: var(--up);
	}
	.neg .net-val {
		color: var(--down);
	}
</style>
