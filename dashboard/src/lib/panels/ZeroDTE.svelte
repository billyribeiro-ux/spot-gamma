<script lang="ts">
	import type { GammaLevels } from '$lib/types';
	import { formatGex } from '$lib/api';

	let { levels }: { levels: GammaLevels } = $props();
	const pct = $derived(Math.round(levels.zero_dte_share * 100));
</script>

<div class="card">
	<h2>0DTE Concentration</h2>
	<div class="big">{pct}%</div>
	<div class="sub">of total |gamma| expires today</div>
	<div class="net" class:pos={levels.zero_dte_net_gex >= 0} class:neg={levels.zero_dte_net_gex < 0}>
		0DTE net GEX: {formatGex(levels.zero_dte_net_gex)}
	</div>
	<div class="meter"><span style:width={pct + '%'}></span></div>
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
	.big {
		font-size: 2.4rem;
		font-weight: 700;
		color: #f3f4f6;
		line-height: 1;
	}
	.sub {
		color: #9ca3af;
		font-size: 0.85rem;
		margin-top: 0.25rem;
	}
	.net {
		margin-top: 0.5rem;
		font-size: 0.85rem;
		font-variant-numeric: tabular-nums;
	}
	.pos {
		color: #4ade80;
	}
	.neg {
		color: #f87171;
	}
	.meter {
		margin-top: 0.75rem;
		height: 8px;
		background: #1f2937;
		border-radius: 4px;
		overflow: hidden;
	}
	.meter span {
		display: block;
		height: 100%;
		background: #22d3ee;
	}
</style>
