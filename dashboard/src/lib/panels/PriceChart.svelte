<script lang="ts">
	import { onMount } from 'svelte';
	import {
		CandlestickSeries,
		ColorType,
		CrosshairMode,
		LineStyle,
		createChart,
		type AutoscaleInfo,
		type CandlestickData,
		type IChartApi,
		type IPriceLine,
		type ISeriesApi,
		type Time,
		type UTCTimestamp
	} from 'lightweight-charts';
	import { fetchHistory, formatGex } from '$lib/api';
	import { theme } from '$lib/theme.svelte';
	import { TIMEFRAMES, type GammaLevels, type Symbol, type Timeframe } from '$lib/types';
	import GexProfile from './GexProfile.svelte';
	import {
		LEVELS,
		allVisible,
		levelRange as computeLevelRange,
		priceDomain as computePriceDomain,
		visibleLevelLines,
		type Visibility
	} from '$lib/levels';

	// `timeframe` is bindable so the command palette (⌘K) can drive it too.
	let {
		symbol,
		levels,
		timeframe = $bindable<Timeframe>('5m')
	}: { symbol: Symbol; levels: GammaLevels; timeframe?: Timeframe } = $props();

	const REFRESH_MS = 30_000;
	const INTRADAY = new Set<Timeframe>(['1m', '5m', '15m', '30m', '1h']);
	const CHART_H = 360;
	let container: HTMLDivElement;
	let error = $state<string | null>(null);
	let lastClose = $state<number | null>(null);
	// Shared price domain so the GEX profile strip aligns with the candle axis.
	let priceDomain = $state<[number, number] | null>(null);

	// Imperative chart handles live outside Svelte reactivity.
	let chart: IChartApi | undefined;
	let series: ISeriesApi<'Candlestick'> | undefined;
	let priceLines: IPriceLine[] = [];
	let ready = $state(false);
	let loadToken = 0;
	// Plain (non-reactive) caches so the effects below only ever *write* state and
	// never read it back — that's what avoids a reactive feedback loop.
	// levelRange: min/max of the level prices; the autoscale unions it in so the
	// walls stay on screen. candleBounds/lastBars: last loaded series.
	let levelRange: { min: number; max: number } | null = null;
	let candleBounds: { lo: number; hi: number } | null = null;
	let lastBars: CandlestickData<Time>[] = [];

	// Level config + range/domain/dedupe math live in $lib/levels (pure + tested).
	let visible = $state<Visibility>(allVisible());

	function recomputeLevelRange() {
		// Only *shown* levels expand the chart, so hiding a far wall lets the
		// price axis zoom back to the candles.
		levelRange = computeLevelRange(levels, visible);
	}

	function recomputeDomain() {
		const d = computePriceDomain(candleBounds, levelRange);
		if (d) priceDomain = d;
	}

	async function load() {
		if (!series) return;
		const token = ++loadToken;
		try {
			const hist = await fetchHistory(symbol, timeframe);
			if (token !== loadToken || !series) return; // a newer request superseded us
			lastBars = hist.bars.map(
				(b): CandlestickData<Time> => ({
					time: b.time as UTCTimestamp,
					open: b.open,
					high: b.high,
					low: b.low,
					close: b.close
				})
			);
			candleBounds = {
				lo: Math.min(...hist.bars.map((b) => b.low)),
				hi: Math.max(...hist.bars.map((b) => b.high))
			};
			recomputeDomain(); // levelRange is maintained by the levels effect
			series.setData(lastBars);
			lastClose = hist.bars.at(-1)?.close ?? hist.meta.last_price ?? null;
			error = null;
			chart?.applyOptions({ timeScale: { timeVisible: INTRADAY.has(timeframe), secondsVisible: false } });
			if (INTRADAY.has(timeframe)) chart?.timeScale().fitContent();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	// Draw the visible gamma levels as labeled price lines, skipping any whose
	// price coincides with one already drawn (dedupes stacked labels).
	function drawLevels() {
		if (!series) return;
		for (const pl of priceLines) series.removePriceLine(pl);
		priceLines = [];
		for (const line of visibleLevelLines(levels, visible)) {
			priceLines.push(
				series.createPriceLine({
					price: line.price,
					color: line.color,
					lineWidth: line.key === 'spot' ? 2 : 1,
					lineStyle: line.key === 'spot' ? LineStyle.Solid : LineStyle.Dashed,
					axisLabelVisible: true,
					title: line.label
				})
			);
		}
	}

	onMount(() => {
		chart = createChart(container, {
			autoSize: true,
			// Pin the locale: lightweight-charts otherwise formats axis labels with
			// navigator.language, which can be a non-Intl tag on some hosts.
			localization: { locale: 'en-US' },
			layout: {
				background: { type: ColorType.Solid, color: 'transparent' },
				textColor: '#a3adc2',
				fontFamily: "'Inter Variable', system-ui, sans-serif"
			},
			grid: {
				vertLines: { color: 'rgba(255,255,255,0.04)' },
				horzLines: { color: 'rgba(255,255,255,0.04)' }
			},
			crosshair: { mode: CrosshairMode.Normal },
			rightPriceScale: { borderColor: 'rgba(255,255,255,0.08)' },
			timeScale: { borderColor: 'rgba(255,255,255,0.08)', timeVisible: true, secondsVisible: false }
		});
		series = chart.addSeries(CandlestickSeries, {
			upColor: '#2ed390',
			downColor: '#ff5269',
			borderUpColor: '#2ed390',
			borderDownColor: '#ff5269',
			wickUpColor: '#69e3b0',
			wickDownColor: '#ff8593',
			// Union the candle range with the level range so the Call/Put walls are
			// always visible, without ever clipping the candles.
			autoscaleInfoProvider: (orig: () => AutoscaleInfo | null) => {
				const base = orig();
				if (!levelRange) return base;
				if (!base?.priceRange) return { priceRange: { minValue: levelRange.min, maxValue: levelRange.max } };
				return {
					priceRange: {
						minValue: Math.min(base.priceRange.minValue, levelRange.min),
						maxValue: Math.max(base.priceRange.maxValue, levelRange.max)
					},
					margins: base.margins
				};
			}
		});
		ready = true;
		applyTheme();
		const id = setInterval(load, REFRESH_MS);
		return () => {
			clearInterval(id);
			chart?.remove();
			chart = series = undefined;
			priceLines = [];
		};
	});

	// Restyle the chart chrome (axes, grid, text) to the active theme tokens.
	function applyTheme() {
		if (!chart) return;
		const css = getComputedStyle(document.documentElement);
		const v = (n: string) => css.getPropertyValue(n).trim();
		const line = v('--grid-line') || 'rgba(255,255,255,0.04)';
		const border = v('--border-strong');
		chart.applyOptions({
			layout: { textColor: v('--text-mid') },
			grid: { vertLines: { color: line }, horzLines: { color: line } },
			rightPriceScale: { borderColor: border },
			timeScale: { borderColor: border }
		});
	}

	// Reload on symbol/timeframe change (and once the chart is ready).
	$effect(() => {
		void symbol;
		void timeframe;
		if (ready) load();
	});

	// Keep chart chrome in sync with the theme.
	$effect(() => {
		void theme.current;
		if (ready) applyTheme();
	});

	// Redraw level overlays + refresh the shared price domain whenever the levels
	// or their visibility change. recomputeLevelRange/drawLevels read both `levels`
	// and `visible`, so this effect re-runs on a toggle; re-setData re-unions the
	// autoscale so hiding a far wall lets the chart zoom back in.
	$effect(() => {
		void levels;
		void visible;
		if (!ready) return;
		recomputeLevelRange();
		recomputeDomain();
		drawLevels();
		if (lastBars.length) series?.setData(lastBars);
	});
</script>

<section class="panel">
	<header>
		<div class="title">
			<h2>Price</h2>
			{#if lastClose != null}<span class="last">{lastClose.toLocaleString()}</span>{/if}
			<span class="gex" class:pos={levels.regime === 'positive'} class:neg={levels.regime === 'negative'}>
				GEX {formatGex(levels.net_gex)}
			</span>
		</div>
		<div class="tfs" role="tablist" aria-label="Timeframe">
			{#each TIMEFRAMES as tf (tf)}
				<button
					role="tab"
					aria-selected={tf === timeframe}
					class:active={tf === timeframe}
					onclick={() => (timeframe = tf)}>{tf}</button
				>
			{/each}
		</div>
	</header>
	<div class="legend">
		{#each LEVELS as d (d.key)}
			{@const present = d.pick(levels) != null}
			<button
				type="button"
				class="chip"
				class:on={visible[d.key] && present}
				disabled={!present}
				aria-pressed={visible[d.key] && present}
				title={present ? `Toggle ${d.label}` : `${d.label} not available`}
				onclick={() => (visible[d.key] = !visible[d.key])}
			>
				<span class="sw" style:background={d.color}></span>{d.label}
			</button>
		{/each}
	</div>
	<div class="chart-row">
		<div class="chart" bind:this={container}></div>
		{#if priceDomain}<GexProfile {levels} {visible} domain={priceDomain} height={CHART_H} />{/if}
	</div>
	{#if error}<p class="err">Chart unavailable — {error}</p>{/if}
</section>

<style>
	.panel {
		background: linear-gradient(180deg, var(--surface-1), var(--bg-1));
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 0.9rem 1rem 0.5rem;
	}
	header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
		flex-wrap: wrap;
		margin-bottom: 0.5rem;
	}
	.title {
		display: flex;
		align-items: baseline;
		gap: 0.6rem;
	}
	h2 {
		margin: 0;
		font-size: 0.95rem;
		color: var(--text-hi);
	}
	.last {
		font-variant-numeric: tabular-nums;
		font-weight: 700;
		color: var(--text-hi);
	}
	.gex {
		font-size: 0.72rem;
		font-weight: 700;
		padding: 0.1rem 0.45rem;
		border-radius: 5px;
		border: 1px solid transparent;
	}
	.gex.pos {
		color: #86efac;
		background: rgba(34, 197, 94, 0.12);
		border-color: rgba(34, 197, 94, 0.4);
	}
	.gex.neg {
		color: #fca5a5;
		background: rgba(239, 68, 68, 0.12);
		border-color: rgba(239, 68, 68, 0.4);
	}
	.tfs {
		display: flex;
		gap: 0.2rem;
	}
	.tfs button {
		background: var(--bg-0);
		color: var(--text-mid);
		border: 1px solid var(--border);
		border-radius: 6px;
		padding: 0.2rem 0.55rem;
		font-size: 0.75rem;
		font-weight: 600;
		cursor: pointer;
	}
	.tfs button.active {
		background: #2563eb;
		color: #fff;
		border-color: #2563eb;
	}
	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
		margin-bottom: 0.5rem;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		background: var(--bg-0);
		border: 1px solid var(--border);
		border-radius: 6px;
		padding: 0.15rem 0.45rem;
		font-size: 0.7rem;
		font-weight: 600;
		color: var(--text-lo);
		cursor: pointer;
	}
	.chip .sw {
		width: 9px;
		height: 9px;
		border-radius: 2px;
		opacity: 0.35;
	}
	.chip.on {
		color: var(--text-hi);
		border-color: var(--border-strong);
	}
	.chip.on .sw {
		opacity: 1;
	}
	.chip:disabled {
		opacity: 0.35;
		cursor: not-allowed;
		text-decoration: line-through;
	}
	.chart-row {
		display: flex;
		gap: 4px;
		align-items: stretch;
	}
	.chart {
		flex: 1 1 auto;
		height: 360px;
		min-width: 0;
	}
	.err {
		color: #fca5a5;
		font-size: 0.8rem;
		margin: 0.25rem 0 0.5rem;
	}
</style>
