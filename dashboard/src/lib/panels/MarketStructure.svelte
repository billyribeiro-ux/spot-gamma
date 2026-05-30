<script lang="ts">
	import { fetchMarketStructure, type MarketStructure } from '$lib/api';
	import type { Symbol } from '$lib/types';

	// Polls the composite market-structure read. Each signal degrades gracefully
	// server-side, so this panel renders whatever is available.
	let { symbol }: { symbol: Symbol } = $props();

	let ms = $state<MarketStructure | null>(null);
	let error = $state(false);

	$effect(() => {
		const sym = symbol;
		let alive = true;
		const load = () =>
			fetchMarketStructure(sym)
				.then((m) => alive && ((ms = m), (error = false)))
				.catch(() => alive && (error = true));
		load();
		const id = setInterval(load, 120_000); // macro/vol moves slowly
		return () => {
			alive = false;
			clearInterval(id);
		};
	});

	// Map a [-1,+1] risk score (−1 risk-on/green … +1 risk-off/red) to a hue.
	const scoreColor = (s: number) =>
		s >= 0.33 ? 'var(--down)' : s <= -0.33 ? 'var(--up)' : 'var(--text-mid)';
	// Gauge needle position 0–100% across the risk-on…risk-off track.
	const gaugePct = (s: number) => ((Math.max(-1, Math.min(1, s)) + 1) / 2) * 100;

	const volColor: Record<string, string> = {
		calm: 'var(--up)',
		normal: 'var(--text-mid)',
		stressed: 'var(--lvl-flip)',
		crisis: 'var(--down)'
	};

	const biasLabel = (b: string) => b.replace('-', ' ').toUpperCase();
</script>

<div class="panel card">
	<div class="head">
		<div class="title">
			<h2>Market Structure</h2>
			<span class="sub">vol · macro · dealer gamma → regime</span>
			<a class="details" href="/market-structure">details →</a>
		</div>
		{#if ms}
			<span class="vol-chip" style:color={volColor[ms.vol_regime]}>{ms.vol_regime.toUpperCase()}</span>
		{/if}
	</div>

	{#if error && !ms}
		<p class="err">Market-structure feed unavailable.</p>
	{:else if !ms}
		<div class="sk"></div>
	{:else}
		<!-- regime gauge -->
		<div class="gauge-row">
			<div class="gauge-meta">
				<span class="bias" style:color={scoreColor(ms.roro_score)}>{biasLabel(ms.bias)}</span>
				<span class="score" style:color={scoreColor(ms.roro_score)}>
					{ms.roro_score >= 0 ? '+' : ''}{ms.roro_score.toFixed(2)}
				</span>
			</div>
			<div class="gauge">
				<span class="track"></span>
				<span class="needle" style:left="{gaugePct(ms.roro_score)}%"></span>
				<span class="g-lab on">risk-on</span>
				<span class="g-lab off">risk-off</span>
			</div>
		</div>

		<div class="flags">
			{#if ms.gamma_available}
				<span class="flag" title="Dealer-gamma conviction gate: >1 trending (act harder), <1 pinned (fade extremes)">
					γ-conviction ×{ms.gamma_modifier.toFixed(2)}
				</span>
			{:else}
				<span class="flag">γ n/a</span>
			{/if}
			{#if ms.divergence}<span class="flag warn">⚠ signal divergence</span>{/if}
			{#if ms.flip_transition_risk}<span class="flag warn">⚠ near gamma flip</span>{/if}
		</div>

		<!-- per-signal breakdown -->
		<ul class="signals">
			{#each ms.signals as s (s.key)}
				<li>
					<span class="s-label">{s.label}</span>
					<span class="s-detail">{s.detail}</span>
					<span class="bar">
						<span class="zero"></span>
						<span
							class="fill"
							style:background={scoreColor(s.score)}
							style:left="{s.score >= 0 ? 50 : 50 + s.score * 50}%"
							style:width="{Math.abs(s.score) * 50}%"
						></span>
					</span>
				</li>
			{/each}
		</ul>

		<!-- §6 context: dispersion + tilt (not part of the directional read) -->
		<div class="context">
			{#if ms.event_risk}
				<span class="ctx" class:hot={ms.event_risk.label !== 'quiet'}>
					<span class="ctx-k">EVENT</span>
					{ms.event_risk.events.length ? ms.event_risk.events.join(' · ') : 'quiet'}
				</span>
			{/if}
			{#if ms.seasonality && ms.seasonality.factors.length}
				<span class="ctx">
					<span class="ctx-k">SEASON</span>
					{ms.seasonality.factors.join(' · ')}
				</span>
			{/if}
			{#if ms.gaps && ms.gaps.today_gap_pct != null}
				<span class="ctx">
					<span class="ctx-k">GAP</span>
					{ms.gaps.today_gap_pct >= 0 ? '+' : ''}{ms.gaps.today_gap_pct}%
					{#if ms.gaps.today_fill_probability != null}
						· {Math.round(ms.gaps.today_fill_probability * 100)}% fill
					{/if}
				</span>
			{/if}
		</div>

		{#if ms.unavailable.length}
			<p class="unavail">unavailable: {ms.unavailable.join(', ')}</p>
		{/if}
	{/if}
</div>

<style>
	.card {
		padding: 1rem 1.2rem;
	}
	.head {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
		margin-bottom: 0.8rem;
	}
	.title {
		display: flex;
		align-items: baseline;
		gap: 0.6rem;
		flex-wrap: wrap;
	}
	h2 {
		margin: 0;
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--text-lo);
		font-weight: 700;
	}
	.sub {
		font-size: 0.72rem;
		color: var(--text-faint);
	}
	.details {
		font-size: 0.7rem;
		font-weight: 600;
		color: var(--accent);
		text-decoration: none;
		transition: color var(--dur-1);
	}
	.details:hover {
		color: var(--text-hi);
	}
	.vol-chip {
		font-size: 0.7rem;
		font-weight: 800;
		letter-spacing: 0.06em;
		padding: 0.15rem 0.55rem;
		border-radius: var(--r-pill);
		border: 1px solid var(--border);
	}
	.gauge-row {
		display: flex;
		align-items: center;
		gap: 1rem;
		margin-bottom: 0.7rem;
	}
	.gauge-meta {
		display: flex;
		flex-direction: column;
		min-width: 5.5rem;
	}
	.bias {
		font-size: 0.78rem;
		font-weight: 800;
		letter-spacing: 0.04em;
	}
	.score {
		font-size: 1.6rem;
		font-weight: 800;
		line-height: 1;
		font-variant-numeric: tabular-nums;
	}
	.gauge {
		position: relative;
		flex: 1;
		height: 22px;
	}
	.track {
		position: absolute;
		top: 9px;
		left: 0;
		right: 0;
		height: 4px;
		border-radius: var(--r-pill);
		background: linear-gradient(90deg, var(--up), var(--surface-3) 50%, var(--down));
	}
	.needle {
		position: absolute;
		top: 2px;
		width: 3px;
		height: 18px;
		border-radius: 2px;
		background: var(--text-hi);
		box-shadow: 0 0 6px var(--text-faint);
		transform: translateX(-50%);
		transition: left var(--dur-3) var(--ease-out);
	}
	.g-lab {
		position: absolute;
		top: 16px;
		font-size: 0.6rem;
		color: var(--text-faint);
	}
	.g-lab.on {
		left: 0;
	}
	.g-lab.off {
		right: 0;
	}
	.flags {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-bottom: 0.8rem;
	}
	.flag {
		font-size: 0.68rem;
		font-weight: 600;
		color: var(--text-lo);
		background: var(--surface-2);
		border: 1px solid var(--border);
		border-radius: var(--r-pill);
		padding: 0.12rem 0.5rem;
	}
	.flag.warn {
		color: var(--lvl-flip);
		border-color: color-mix(in oklab, var(--lvl-flip) 40%, transparent);
	}
	.signals {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
	}
	.signals li {
		display: grid;
		grid-template-columns: 6.5rem 1fr 90px;
		align-items: center;
		gap: 0.6rem;
		font-size: 0.78rem;
	}
	.s-label {
		font-weight: 700;
		color: var(--text-hi);
		text-transform: capitalize;
	}
	.s-detail {
		color: var(--text-lo);
		font-size: 0.72rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.bar {
		position: relative;
		height: 8px;
		background: var(--surface-2);
		border-radius: var(--r-pill);
		overflow: hidden;
	}
	.zero {
		position: absolute;
		left: 50%;
		top: 0;
		bottom: 0;
		width: 1px;
		background: var(--border-strong);
	}
	.fill {
		position: absolute;
		top: 0;
		bottom: 0;
		border-radius: var(--r-pill);
		transition:
			left var(--dur-3) var(--ease-out),
			width var(--dur-3) var(--ease-out);
	}
	.context {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-top: 0.85rem;
		padding-top: 0.7rem;
		border-top: 1px solid var(--border);
	}
	.ctx {
		font-size: 0.7rem;
		color: var(--text-mid);
		background: var(--surface-2);
		border: 1px solid var(--border);
		border-radius: var(--r-pill);
		padding: 0.15rem 0.55rem;
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
	}
	.ctx-k {
		font-size: 0.6rem;
		font-weight: 700;
		letter-spacing: 0.06em;
		color: var(--text-lo);
	}
	.ctx.hot {
		color: var(--lvl-flip);
		border-color: color-mix(in oklab, var(--lvl-flip) 40%, transparent);
	}
	.unavail {
		margin: 0.7rem 0 0;
		font-size: 0.68rem;
		color: var(--text-faint);
	}
	.err {
		color: var(--down);
		font-size: 0.85rem;
		margin: 0;
	}
	.sk {
		height: 160px;
		border-radius: var(--r-sm);
		background: var(--surface-1);
		animation: pulse 1.4s ease-in-out infinite;
	}
	@keyframes pulse {
		50% {
			opacity: 0.5;
		}
	}
</style>
