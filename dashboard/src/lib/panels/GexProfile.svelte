<script lang="ts">
	import { scaleLinear } from 'd3-scale';
	import { max } from 'd3-array';
	import type { GammaLevels } from '$lib/types';

	// A slim net-GEX-by-price histogram pinned to the SAME price domain as the
	// candle chart beside it, so the two read as one SpotGamma-style panel.
	let {
		levels,
		domain,
		height = 360,
		visible = {}
	}: {
		levels: GammaLevels;
		domain: [number, number];
		height?: number;
		visible?: Record<string, boolean>;
	} = $props();

	// Only mark levels that are toggled on in the chart (default: shown).
	const show = (key: string) => visible[key] !== false;

	const W = 104;
	// Insets roughly match lightweight-charts' plot area (time axis reserved at the
	// bottom) so bars line up with the candles' price axis.
	const TOP = 6;
	const BOTTOM = 30;
	const GUTTER = 8;

	const rows = $derived(
		levels.by_strike
			.filter((s) => s.strike >= domain[0] && s.strike <= domain[1])
			.map((s) => ({ strike: s.strike, net: s.call_gex + s.put_gex }))
	);
	const y = $derived(scaleLinear().domain(domain).range([height - BOTTOM, TOP]));
	const x = $derived(
		scaleLinear()
			.domain([0, max(rows, (d) => Math.abs(d.net)) ?? 1])
			.range([0, W - GUTTER - 4])
	);
	const rowH = $derived(
		rows.length ? Math.max(1.5, ((height - TOP - BOTTOM) / rows.length) * 0.82) : 2
	);

	// Mark the (visible) key levels with a small colored tick on the price axis.
	const ticks = $derived(
		(
			[
				['spot', levels.spot, '#e5e7eb'],
				['call_wall', levels.call_wall, '#22c55e'],
				['put_wall', levels.put_wall, '#ef4444'],
				['abs_gamma', levels.absolute_gamma, '#06b6d4'],
				['hedge_wall', levels.hedge_wall, '#fb923c']
			] as Array<[string, number | null, string]>
		)
			.filter(([key, p]) => show(key) && p != null && (p as number) >= domain[0] && (p as number) <= domain[1])
			.map(([, p, color]) => ({ yy: y(p as number), color }))
	);
</script>

<div class="profile">
	<span class="cap">GEX</span>
	<svg viewBox="0 0 {W} {height}" width={W} {height} role="img" aria-label="Net GEX by price">
		{#each ticks as t (t.color)}
			<line x1="0" x2={W} y1={t.yy} y2={t.yy} stroke={t.color} opacity="0.18" />
		{/each}
		{#each rows as d (d.strike)}
			<rect
				x={GUTTER}
				y={(y(d.strike) ?? 0) - rowH / 2}
				width={x(Math.abs(d.net))}
				height={rowH}
				fill={d.net >= 0 ? '#22c55e' : '#ef4444'}
				opacity="0.8"
			/>
		{/each}
	</svg>
</div>

<style>
	.profile {
		position: relative;
		flex: 0 0 104px;
	}
	.cap {
		position: absolute;
		top: 2px;
		left: 8px;
		font-size: 0.62rem;
		letter-spacing: 0.08em;
		color: #6b7280;
		font-weight: 700;
	}
	svg {
		display: block;
	}
</style>
