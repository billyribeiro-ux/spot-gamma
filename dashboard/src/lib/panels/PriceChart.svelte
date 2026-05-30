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
	import { TIMEFRAMES, type GammaLevels, type Symbol, type Timeframe } from '$lib/types';
	import GexProfile from './GexProfile.svelte';

	let { symbol, levels }: { symbol: Symbol; levels: GammaLevels } = $props();

	const REFRESH_MS = 30_000;
	const INTRADAY = new Set<Timeframe>(['1m', '5m', '15m', '30m', '1h']);
	const CHART_H = 360;

	let timeframe = $state<Timeframe>('5m');
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

	function recomputeLevelRange() {
		const ps = [
			levels.spot,
			levels.call_wall,
			levels.put_wall,
			levels.zero_gamma,
			levels.volatility_trigger,
			levels.absolute_gamma,
			levels.hedge_wall
		].filter((v): v is number => v != null);
		levelRange = ps.length ? { min: Math.min(...ps), max: Math.max(...ps) } : null;
	}

	function recomputeDomain() {
		const los = [candleBounds?.lo, levelRange?.min].filter((v): v is number => v != null);
		const his = [candleBounds?.hi, levelRange?.max].filter((v): v is number => v != null);
		if (!los.length || !his.length) return;
		const lo = Math.min(...los);
		const hi = Math.max(...his);
		const pad = (hi - lo) * 0.02 || 1;
		priceDomain = [lo - pad, hi + pad];
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

	// Draw the gamma levels as labeled horizontal price lines.
	function drawLevels() {
		if (!series) return;
		for (const pl of priceLines) series.removePriceLine(pl);
		priceLines = [];
		// SpotGamma-style key levels, overlaid as labeled price lines.
		const lines: Array<[number | null, string, string]> = [
			[levels.spot, '#e5e7eb', 'Spot'],
			[levels.call_wall, '#22c55e', 'Call Wall'],
			[levels.put_wall, '#ef4444', 'Put Wall'],
			[levels.zero_gamma, '#f59e0b', 'Gamma Flip'],
			[levels.volatility_trigger, '#a855f7', 'Vol Trigger'],
			[levels.absolute_gamma, '#06b6d4', 'Abs Gamma'],
			[levels.hedge_wall, '#fb923c', 'Hedge Wall']
		];
		for (const [price, color, title] of lines) {
			if (price == null) continue;
			priceLines.push(
				series.createPriceLine({
					price,
					color,
					lineWidth: title === 'Spot' ? 2 : 1,
					lineStyle: title === 'Spot' ? LineStyle.Solid : LineStyle.Dashed,
					axisLabelVisible: true,
					title
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
				textColor: '#9ca3af',
				fontFamily: 'system-ui, sans-serif'
			},
			grid: {
				vertLines: { color: 'rgba(148,163,184,0.06)' },
				horzLines: { color: 'rgba(148,163,184,0.06)' }
			},
			crosshair: { mode: CrosshairMode.Normal },
			rightPriceScale: { borderColor: 'rgba(148,163,184,0.15)' },
			timeScale: { borderColor: 'rgba(148,163,184,0.15)', timeVisible: true, secondsVisible: false }
		});
		series = chart.addSeries(CandlestickSeries, {
			upColor: '#22c55e',
			downColor: '#ef4444',
			borderUpColor: '#22c55e',
			borderDownColor: '#ef4444',
			wickUpColor: '#4ade80',
			wickDownColor: '#f87171',
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
		const id = setInterval(load, REFRESH_MS);
		return () => {
			clearInterval(id);
			chart?.remove();
			chart = series = undefined;
			priceLines = [];
		};
	});

	// Reload on symbol/timeframe change (and once the chart is ready).
	$effect(() => {
		void symbol;
		void timeframe;
		if (ready) load();
	});

	// Redraw level overlays + refresh the shared price domain whenever levels
	// change. Re-setData so the autoscale re-unions the (possibly moved) walls.
	$effect(() => {
		void levels;
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
	<div class="chart-row">
		<div class="chart" bind:this={container}></div>
		{#if priceDomain}<GexProfile {levels} domain={priceDomain} height={CHART_H} />{/if}
	</div>
	{#if error}<p class="err">Chart unavailable — {error}</p>{/if}
</section>

<style>
	.panel {
		background: #111827;
		border: 1px solid #1f2937;
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
		color: #e5e7eb;
	}
	.last {
		font-variant-numeric: tabular-nums;
		font-weight: 700;
		color: #f3f4f6;
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
		background: #0b0f17;
		color: #9ca3af;
		border: 1px solid #1f2937;
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
