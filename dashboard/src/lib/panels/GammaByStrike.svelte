<script lang="ts">
	import { scaleBand, scaleLinear } from 'd3-scale';
	import { max } from 'd3-array';
	import { formatGex } from '$lib/api';
	import type { GammaLevels } from '$lib/types';

	let { levels }: { levels: GammaLevels } = $props();

	const W = 720;
	const M = { top: 8, right: 16, bottom: 28, left: 64 };
	const ROW = 14;
	const MAX_ROWS = 70;

	interface Row {
		strike: number;
		net: number;
	}

	// Strikes within a spot-centered window (anchored to the walls when known),
	// capped for legibility and sorted high->low so price reads top-to-bottom.
	const rows = $derived.by<Row[]>(() => {
		const lo = (levels.put_wall ?? levels.spot * 0.92) * 0.99;
		const hi = (levels.call_wall ?? levels.spot * 1.08) * 1.01;
		let r = levels.by_strike
			.filter((s) => s.strike >= lo && s.strike <= hi)
			.map((s) => ({ strike: s.strike, net: s.call_gex + s.put_gex }));
		if (r.length > MAX_ROWS) {
			// keep the highest-magnitude strikes so the structure survives the cap
			const keep = new Set(
				[...r].sort((a, b) => Math.abs(b.net) - Math.abs(a.net)).slice(0, MAX_ROWS).map((x) => x.strike)
			);
			r = r.filter((x) => keep.has(x.strike));
		}
		return r.sort((a, b) => b.strike - a.strike);
	});

	const height = $derived(Math.max(120, rows.length * ROW + M.top + M.bottom));
	const x = $derived(
		scaleLinear()
			.domain([-(max(rows, (d) => Math.abs(d.net)) ?? 1), max(rows, (d) => Math.abs(d.net)) ?? 1])
			.range([M.left, W - M.right])
	);
	const y = $derived(
		scaleBand<number>()
			.domain(rows.map((d) => d.strike))
			.range([M.top, height - M.bottom])
			.padding(0.2)
	);
	const zeroX = $derived(x(0));

	// Horizontal guide lines for the key levels (mapped from strike -> y).
	const guides = $derived(
		(
			[
				[levels.spot, '#e5e7eb', 'Spot'],
				[levels.call_wall, '#22c55e', 'Call Wall'],
				[levels.put_wall, '#ef4444', 'Put Wall'],
				[levels.zero_gamma, '#f59e0b', 'Zero Γ']
			] as Array<[number | null, string, string]>
		)
			.filter(([p]) => p != null)
			.map(([p, color, label]) => ({ yPos: yForPrice(p as number), color, label }))
			.filter((g) => g.yPos != null)
	);

	// Interpolate a price onto the banded strike axis so guides sit between rows.
	function yForPrice(price: number): number | null {
		if (rows.length === 0) return null;
		const hi = rows[0].strike;
		const lo = rows[rows.length - 1].strike;
		if (price > hi || price < lo) return null;
		const t = (hi - price) / (hi - lo || 1);
		return M.top + t * (height - M.top - M.bottom);
	}
</script>

<section class="panel">
	<header>
		<h2>Net gamma by strike</h2>
		<span class="legend"><i class="call"></i> dealer long &nbsp; <i class="put"></i> dealer short</span>
	</header>
	{#if rows.length === 0}
		<p class="empty">No strikes in range.</p>
	{:else}
		<svg viewBox="0 0 {W} {height}" width="100%" height={height} role="img" aria-label="Net gamma by strike">
			<!-- guide lines -->
			{#each guides as g (g.label)}
				<line class="guide" x1={M.left} x2={W - M.right} y1={g.yPos} y2={g.yPos} style:stroke={g.color} />
				<text x={W - M.right} y={(g.yPos ?? 0) - 2} style:fill={g.color} font-size="9" text-anchor="end">{g.label}</text>
			{/each}
			<!-- zero axis -->
			<line class="axis" x1={zeroX} x2={zeroX} y1={M.top} y2={height - M.bottom} />
			<!-- bars -->
			{#each rows as d (d.strike)}
				{@const w = Math.abs(x(d.net) - zeroX)}
				<rect
					class="bar"
					class:pos={d.net >= 0}
					class:neg={d.net < 0}
					x={d.net >= 0 ? zeroX : zeroX - w}
					y={y(d.strike)}
					width={w}
					height={y.bandwidth()}
				>
					<title>{d.strike.toLocaleString()} · {formatGex(d.net)}</title>
				</rect>
			{/each}
			<!-- strike labels (every Nth to avoid crowding) -->
			{#each rows as d, i (d.strike)}
				{#if i % Math.ceil(rows.length / 18) === 0}
					<text class="tick" x={M.left - 6} y={(y(d.strike) ?? 0) + y.bandwidth()} font-size="9" text-anchor="end">
						{d.strike.toLocaleString()}
					</text>
				{/if}
			{/each}
			<!-- x ticks -->
			{#each x.ticks(5) as t (t)}
				<text class="tick" x={x(t)} y={height - 10} font-size="9" text-anchor="middle">{formatGex(t)}</text>
			{/each}
		</svg>
	{/if}
</section>

<style>
	.panel {
		padding: 0.95rem 1.1rem;
	}
	header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.6rem;
	}
	h2 {
		margin: 0;
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--text-lo);
		font-weight: 700;
	}
	.legend {
		font-size: 0.72rem;
		color: var(--text-lo);
		display: flex;
		align-items: center;
	}
	.legend i {
		display: inline-block;
		width: 9px;
		height: 9px;
		border-radius: 2px;
		margin-right: 3px;
	}
	.legend .call {
		background: var(--up);
	}
	.legend .put {
		background: var(--down);
	}
	.empty {
		color: var(--text-lo);
		font-size: 0.85rem;
	}
	svg {
		display: block;
	}
	.bar {
		opacity: 0.85;
		transition: opacity var(--dur-1);
	}
	.bar.pos {
		fill: var(--up);
	}
	.bar.neg {
		fill: var(--down);
	}
	.bar:hover {
		opacity: 1;
	}
	.guide {
		stroke-dasharray: 3 3;
		opacity: 0.45;
	}
	.axis {
		stroke: var(--border-strong);
	}
	.tick {
		fill: var(--text-lo);
	}
</style>
