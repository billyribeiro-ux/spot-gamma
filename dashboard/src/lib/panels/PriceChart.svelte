<script lang="ts">
	import { onMount } from 'svelte';
	import {
		CandlestickSeries,
		ColorType,
		CrosshairMode,
		LineStyle,
		createChart,
		type CandlestickData,
		type IChartApi,
		type IPriceLine,
		type ISeriesApi,
		type Time,
		type UTCTimestamp
	} from 'lightweight-charts';
	import { fetchHistory } from '$lib/api';
	import { TIMEFRAMES, type GammaLevels, type Symbol, type Timeframe } from '$lib/types';

	let { symbol, levels }: { symbol: Symbol; levels: GammaLevels } = $props();

	const REFRESH_MS = 30_000;
	const INTRADAY = new Set<Timeframe>(['1m', '5m', '15m', '30m', '1h']);

	let timeframe = $state<Timeframe>('5m');
	let container: HTMLDivElement;
	let error = $state<string | null>(null);
	let lastClose = $state<number | null>(null);

	// Imperative chart handles live outside Svelte reactivity.
	let chart: IChartApi | undefined;
	let series: ISeriesApi<'Candlestick'> | undefined;
	let priceLines: IPriceLine[] = [];
	let ready = $state(false);
	let loadToken = 0;

	async function load() {
		if (!series) return;
		const token = ++loadToken;
		try {
			const hist = await fetchHistory(symbol, timeframe);
			if (token !== loadToken || !series) return; // a newer request superseded us
			series.setData(
				hist.bars.map(
					(b): CandlestickData<Time> => ({
						time: b.time as UTCTimestamp,
						open: b.open,
						high: b.high,
						low: b.low,
						close: b.close
					})
				)
			);
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
		const lines: Array<[number | null, string, string]> = [
			[levels.spot, '#e5e7eb', 'Spot'],
			[levels.call_wall, '#22c55e', 'Call Wall'],
			[levels.put_wall, '#ef4444', 'Put Wall'],
			[levels.zero_gamma, '#f59e0b', 'Zero Γ'],
			[levels.volatility_trigger, '#a855f7', 'Vol Trigger']
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
			wickDownColor: '#f87171'
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

	// Redraw level overlays whenever levels change.
	$effect(() => {
		void levels;
		if (ready) drawLevels();
	});
</script>

<section class="panel">
	<header>
		<div class="title">
			<h2>Price</h2>
			{#if lastClose != null}<span class="last">{lastClose.toLocaleString()}</span>{/if}
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
	<div class="chart" bind:this={container}></div>
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
	.chart {
		width: 100%;
		height: 360px;
	}
	.err {
		color: #fca5a5;
		font-size: 0.8rem;
		margin: 0.25rem 0 0.5rem;
	}
</style>
