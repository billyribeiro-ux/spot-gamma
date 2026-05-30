<script lang="ts">
	import type { GammaLevels } from '$lib/types';
	import { formatGex } from '$lib/api';

	let { levels }: { levels: GammaLevels } = $props();

	// Show a window of strikes around spot so the profile is legible.
	const WINDOW = 0.06;
	const visible = $derived(
		levels.by_strike
			.filter((s) => Math.abs(s.strike - levels.spot) / levels.spot <= WINDOW)
			.slice()
			.sort((a, b) => b.strike - a.strike)
	);
	const maxAbs = $derived(Math.max(1, ...visible.map((s) => Math.abs(s.call_gex + s.put_gex))));

	function net(s: { call_gex: number; put_gex: number }): number {
		return s.call_gex + s.put_gex;
	}
	// Half-width percentage for a bar, centered on the zero axis.
	function width(s: { call_gex: number; put_gex: number }): number {
		return (Math.abs(net(s)) / maxAbs) * 50;
	}
	function nearest(strike: number, level: number | null, step: number): boolean {
		return level !== null && Math.abs(strike - level) <= step / 2;
	}

	const step = $derived(
		visible.length > 1 ? Math.abs(visible[0].strike - visible[1].strike) : 1
	);
</script>

<div class="card">
	<h2>Net Gamma by Strike</h2>
	<div class="rows">
		{#each visible as s (s.strike)}
			{@const n = net(s)}
			<div class="row" class:spot={nearest(s.strike, levels.spot, step)}>
				<span class="strike">{s.strike.toLocaleString()}</span>
				<div class="track">
					<span class="axis"></span>
					<span
						class="bar"
						class:pos={n >= 0}
						class:neg={n < 0}
						style:width={width(s) + '%'}
						style:left={n >= 0 ? '50%' : 50 - width(s) + '%'}
						title={formatGex(n)}
					></span>
					{#if nearest(s.strike, levels.call_wall, step)}<span class="flag cw">Call Wall</span>{/if}
					{#if nearest(s.strike, levels.put_wall, step)}<span class="flag pw">Put Wall</span>{/if}
					{#if nearest(s.strike, levels.volatility_trigger, step)}<span class="flag vt">Vol Trigger</span>{/if}
				</div>
			</div>
		{/each}
	</div>
	<p class="legend"><span class="sw neg"></span> net short gamma &nbsp; <span class="sw pos"></span> net long gamma</p>
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
	.row {
		display: grid;
		grid-template-columns: 64px 1fr;
		align-items: center;
		gap: 0.5rem;
		height: 20px;
	}
	.row.spot {
		background: rgba(255, 255, 255, 0.05);
		border-radius: 4px;
	}
	.strike {
		font-size: 0.78rem;
		color: #9ca3af;
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	.track {
		position: relative;
		height: 14px;
	}
	.axis {
		position: absolute;
		left: 50%;
		top: 0;
		bottom: 0;
		width: 1px;
		background: #374151;
	}
	.bar {
		position: absolute;
		top: 2px;
		height: 10px;
		border-radius: 2px;
	}
	.bar.pos {
		background: #22c55e;
	}
	.bar.neg {
		background: #ef4444;
	}
	.flag {
		position: absolute;
		top: -1px;
		right: 4px;
		font-size: 0.6rem;
		font-weight: 700;
		padding: 0 4px;
		border-radius: 3px;
		color: #0b0f17;
	}
	.flag.cw {
		background: #ef4444;
		color: #fff;
	}
	.flag.pw {
		background: #22c55e;
		color: #0b0f17;
	}
	.flag.vt {
		background: #22d3ee;
		right: 70px;
		color: #0b0f17;
	}
	.legend {
		margin: 0.6rem 0 0;
		font-size: 0.72rem;
		color: #6b7280;
	}
	.sw {
		display: inline-block;
		width: 10px;
		height: 10px;
		border-radius: 2px;
		vertical-align: middle;
	}
	.sw.pos {
		background: #22c55e;
	}
	.sw.neg {
		background: #ef4444;
	}
</style>
