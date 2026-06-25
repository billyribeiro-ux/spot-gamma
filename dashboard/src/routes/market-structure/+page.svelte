<script lang="ts">
	import { fly } from 'svelte/transition';
	import { expoOut } from 'svelte/easing';
	import { fetchMarketStructure, type MarketStructure } from '$lib/api';
	import { SYMBOLS, type Symbol } from '$lib/types';
	import { motionOK, stagger } from '$lib/motion';
	import { theme } from '$lib/theme.svelte';

	const REFRESH_MS = 120_000; // macro/vol moves slowly

	let symbol = $state<Symbol>('SPX');
	let ms = $state<MarketStructure | null>(null);
	let error = $state(false);
	let updatedAt = $state('');

	const activeIndex = $derived(SYMBOLS.indexOf(symbol));
	const D = motionOK() ? 1 : 0;
	const enter = (i: number) => ({
		y: 14,
		opacity: 0,
		duration: 460 * D,
		delay: stagger(i) * D,
		easing: expoOut
	});

	// Reload on symbol change, then poll. Each signal degrades gracefully
	// server-side, so we render whatever is available.
	$effect(() => {
		const sym = symbol;
		let alive = true;
		const load = () =>
			fetchMarketStructure(sym)
				.then((m) => {
					if (!alive) return;
					ms = m;
					error = false;
					updatedAt = new Date().toLocaleTimeString('en-US');
				})
				.catch(() => {
					if (alive) error = true;
				});
		load();
		const id = setInterval(load, REFRESH_MS);
		return () => {
			alive = false;
			clearInterval(id);
		};
	});

	// Map a [-1,+1] risk score (−1 risk-on/green … +1 risk-off/red) to a token color.
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
	const pct = (n: number) => `${Math.round(n * 100)}%`;
	const signed = (n: number, digits = 2) => `${n >= 0 ? '+' : ''}${n.toFixed(digits)}`;

	// γ-modifier (0.5…1.5) → conviction phrase on the volatility-regime axis.
	const gammaPhrase = (m: number) =>
		m >= 1.15 ? 'trending — act harder' : m <= 0.85 ? 'pinned — fade extremes' : 'neutral';

	// Format a fractional return as a signed percentage, e.g. 0.0182 → "+1.82%".
	const retPct = (n: number, digits = 2) => `${n >= 0 ? '+' : ''}${(n * 100).toFixed(digits)}%`;
</script>

<svelte:head><title>Spot Gamma — Market Structure · {symbol}</title></svelte:head>

<header class="appbar">
	<a class="brand" href="/">
		<span class="mark">Γ</span>
		<span class="word">SPOT<b>GAMMA</b></span>
	</a>

	<nav class="seg" style="--n: {SYMBOLS.length}; --i: {activeIndex}" aria-label="Symbol">
		<span class="seg-ind" aria-hidden="true"></span>
		{#each SYMBOLS as s (s)}
			<button class:active={s === symbol} aria-pressed={s === symbol} onclick={() => (symbol = s)}
				>{s}</button
			>
		{/each}
	</nav>

	<div class="status">
		<span class="live" class:on={!error}><i></i>{error ? 'OFFLINE' : 'LIVE'}</span>
		{#if updatedAt}<span class="updated mono">{updatedAt}</span>{/if}
		<button class="icon-btn" onclick={() => theme.toggle()} aria-label="Toggle theme" title="Toggle theme">
			{#if theme.current === 'dark'}
				<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.5" /><g class="rays"><line x1="12" y1="2" x2="12" y2="5" /><line x1="12" y1="19" x2="12" y2="22" /><line x1="2" y1="12" x2="5" y2="12" /><line x1="19" y1="12" x2="22" y2="12" /><line x1="4.9" y1="4.9" x2="7" y2="7" /><line x1="17" y1="17" x2="19.1" y2="19.1" /><line x1="4.9" y1="19.1" x2="7" y2="17" /><line x1="17" y1="7" x2="19.1" y2="4.9" /></g></svg>
			{:else}
				<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>
			{/if}
		</button>
		<a class="conn" href="/">← Dashboard</a>
	</div>
</header>

<main>
	<div class="page-head" in:fly={enter(0)}>
		<div>
			<h1>Market Structure</h1>
			<p class="lede">
				A transparent regime read — volatility, cross-asset macro, and dealer gamma fused into a
				risk-on/risk-off bias and a conviction gate. Every component stays independently visible so
				you can disagree with the blend.
			</p>
		</div>
	</div>

	{#if error && !ms}
		<div class="error" in:fly={enter(1)}>
			<strong>Market-structure feed unavailable.</strong>
			<div class="hint">Is the API running? <code>uvicorn api.main:app --port 8000</code></div>
		</div>
	{:else if !ms}
		<div class="skeletons">
			<div class="sk sk-hero"></div>
			<div class="sk sk-wide"></div>
			<div class="sk sk-wide"></div>
		</div>
	{:else}
		<!-- 1 · hero regime gauge -->
		<section class="panel hero" in:fly={enter(1)}>
			<div class="hero-main">
				<div class="hero-meta">
					<span class="bias" style:color={scoreColor(ms.roro_score)}>{biasLabel(ms.bias)}</span>
					<span class="score mono" style:color={scoreColor(ms.roro_score)}>
						{signed(ms.roro_score)}
					</span>
					<span class="score-cap">RORO score · −1 risk-on … +1 risk-off</span>
				</div>
				<div class="gauge">
					<span class="track"></span>
					<span class="needle" style:left="{gaugePct(ms.roro_score)}%"></span>
					<span class="g-lab on">risk-on</span>
					<span class="g-lab mid">neutral</span>
					<span class="g-lab off">risk-off</span>
				</div>
			</div>

			<div class="hero-stats">
				<div class="stat">
					<span class="k">Vol regime</span>
					<span class="v" style:color={volColor[ms.vol_regime]}>{ms.vol_regime.toUpperCase()}</span>
				</div>
				<div class="stat">
					<span class="k">Actionability</span>
					<span class="v mono">{ms.actionability.toFixed(2)}</span>
					<span class="sub-k">|roro| × γ</span>
				</div>
				<div class="stat">
					<span class="k">γ conviction</span>
					{#if ms.gamma_available}
						<span class="v mono">×{ms.gamma_modifier.toFixed(2)}</span>
						<span class="sub-k">{gammaPhrase(ms.gamma_modifier)}</span>
					{:else}
						<span class="v na">n/a</span>
						<span class="sub-k">gamma unavailable</span>
					{/if}
				</div>
				<div class="stat">
					<span class="k">Regime score</span>
					<span class="v mono" style:color={scoreColor(ms.regime_score)}>{signed(ms.regime_score)}</span>
					<span class="sub-k">sign(roro) × actionability</span>
				</div>
			</div>

			<div class="flags">
				<span
					class="flag"
					title="Dealer-gamma conviction gate on the volatility-regime axis. >1 trending (act harder), <1 pinned (fade extremes). It never flips the signed direction."
				>
					{#if ms.gamma_available}γ-conviction ×{ms.gamma_modifier.toFixed(2)}{:else}γ n/a{/if}
				</span>
				{#if ms.divergence}
					<span class="flag warn" title="Components disagree — an instability warning, not a direction."
						>⚠ signal divergence</span
					>
				{/if}
				{#if ms.flip_transition_risk}
					<span class="flag warn" title="Spot near the zero-gamma flip — the regime read is weakest at transitions."
						>⚠ near gamma flip</span
					>
				{/if}
			</div>
		</section>

		<!-- 2 · full signal breakdown -->
		<section class="panel block" in:fly={enter(2)}>
			<div class="block-head">
				<h2>Signal breakdown</h2>
				<span class="block-sub">every component, scored and oriented (+ = risk-off, − = risk-on)</span>
			</div>
			<ul class="signals">
				{#each ms.signals as s (s.key)}
					<li>
						<div class="s-top">
							<span class="s-label">{s.label}</span>
							<span class="s-bias" style:color={scoreColor(s.score)}>{biasLabel(s.bias)}</span>
							<span class="s-score mono" style:color={scoreColor(s.score)}>{signed(s.score)}</span>
						</div>
						<span class="bar">
							<span class="zero"></span>
							<span
								class="fill"
								style:background={scoreColor(s.score)}
								style:left="{s.score >= 0 ? 50 : 50 + s.score * 50}%"
								style:width="{Math.abs(s.score) * 50}%"
							></span>
						</span>
						<span class="s-detail">{s.detail}</span>
					</li>
				{/each}
			</ul>
			{#if ms.unavailable.length}
				<p class="unavail">unavailable signals: {ms.unavailable.join(', ')}</p>
			{/if}
		</section>

		<!-- 2b · learned overlay (§7) — only when a validated model artifact exists -->
		{#if ms.learned}
			<section class="panel block learned" in:fly={enter(2)}>
				<div class="block-head">
					<h2>Learned overlay</h2>
					<span class="block-sub">§7 · out-of-sample validated — measured, not a forecast</span>
				</div>
				<div class="ctx-lead">
					<span class="ctx-pill">{ms.learned.horizon}d horizon</span>
					<span class="ctx-sc mono">OOS IC {signed(ms.learned.oos_ic)}</span>
					{#if ms.learned.trained_through}
						<span class="ctx-sc">trained through {ms.learned.trained_through}</span>
					{/if}
				</div>
				<div class="learned-grid">
					<div class="stat">
						<span class="k">Weights</span>
						{#if ms.learned.adopt_weights}
							<span class="v" style:font-size="0.95rem">calibrated (beat prior OOS)</span>
							<span class="sub-k">reliability-reweighted, shrunk to the §5 prior</span>
						{:else}
							<span class="v" style:font-size="0.95rem">documented prior</span>
							<span class="sub-k">calibrated weights did not beat the prior OOS</span>
						{/if}
					</div>
					<div class="stat">
						<span class="k">{ms.learned.horizon}d return tilt</span>
						{#if ms.learned.adopt_tilt && ms.learned.tilt_fwd_return != null}
							<span
								class="v mono"
								style:color={scoreColor(-ms.learned.tilt_fwd_return)}
								title="A contrarian ridge estimate of the forward return — a separate overlay, never merged into the regime read."
							>
								{retPct(ms.learned.tilt_fwd_return)}
							</span>
							<span class="sub-k">contrarian ridge estimate (separate from the regime read)</span>
						{:else}
							<span class="v na">not adopted</span>
							<span class="sub-k">no out-of-sample edge cleared the floor</span>
						{/if}
					</div>
					{#if ms.learned.calibration}
						<div class="stat">
							<span class="k">This regime, historically</span>
							<span class="v mono" style:color={scoreColor(-ms.learned.calibration.mean_fwd)}>
								{retPct(ms.learned.calibration.mean_fwd)}
							</span>
							<span class="sub-k">
								mean {ms.learned.horizon}d fwd · {pct(ms.learned.calibration.pct_positive)} positive · n={ms
									.learned.calibration.n}
							</span>
						</div>
					{/if}
				</div>
				<p class="note">
					The composite carries real but <strong>contrarian</strong> forward-return information at this
					horizon (a risk-off reading has preceded higher returns — mean reversion). The regime read
					above still describes <strong>state, not return</strong>; this overlay is adopted only where it
					beats the documented prior out-of-sample, and is shown separately on purpose.
				</p>
			</section>
		{/if}

		<!-- 3 · context: event risk, seasonality, gaps -->
		<section class="ctx-grid">
			<div class="panel block" in:fly={enter(3)}>
				<div class="block-head">
					<h2>Event risk</h2>
					<span class="block-sub">gates dispersion, not direction</span>
				</div>
				{#if ms.event_risk}
					<div class="ctx-lead" class:hot={ms.event_risk.label !== 'quiet'}>
						<span class="ctx-pill">{ms.event_risk.label.toUpperCase()}</span>
						<span class="ctx-sc mono">score {ms.event_risk.score.toFixed(2)}</span>
					</div>
					<ul class="chips">
						{#each ms.event_risk.events as ev (ev)}
							<li>{ev}</li>
						{:else}
							<li class="muted">no scheduled high-impact events</li>
						{/each}
					</ul>
					<p class="note">
						Scheduled events raise expected |daily return| (dispersion), they do not tell you which
						way. Feed-required events (FOMC/CPI/PCE) are absent unless wired, never formula-faked.
					</p>
				{:else}
					<p class="muted">Event-risk data unavailable.</p>
				{/if}
			</div>

			<div class="panel block" in:fly={enter(4)}>
				<div class="block-head">
					<h2>Seasonality</h2>
					<span class="block-sub">a small tilt, not a thesis</span>
				</div>
				{#if ms.seasonality}
					<div class="ctx-lead">
						<span
							class="ctx-pill"
							style:color={ms.seasonality.tilt > 0
								? 'var(--up)'
								: ms.seasonality.tilt < 0
									? 'var(--down)'
									: 'var(--text-mid)'}>{ms.seasonality.label.toUpperCase()}</span
						>
						<span class="ctx-sc mono">tilt {signed(ms.seasonality.tilt)}</span>
					</div>
					<ul class="chips">
						{#each ms.seasonality.factors as f (f)}
							<li>{f}</li>
						{:else}
							<li class="muted">no active seasonal factors</li>
						{/each}
					</ul>
					<p class="note">
						Only effects with both replication and a mechanism feed the tilt (turn-of-month, faint
						pre-holiday); day-of-week / Santa / Sell-in-May are excluded. The magnitude is capped
						small on purpose.
					</p>
				{:else}
					<p class="muted">Seasonality data unavailable.</p>
				{/if}
			</div>

			<!-- 3b · the killer gap statistics table -->
			<div class="panel block gaps" in:fly={enter(5)}>
				<div class="block-head">
					<h2>Gap statistics</h2>
					<span class="block-sub">fill rate conditioned on gap size</span>
				</div>
				{#if ms.gaps}
					{#if ms.gaps.today_gap_pct != null}
						<div class="ctx-lead">
							<span class="ctx-pill">TODAY {signed(ms.gaps.today_gap_pct, 2)}%</span>
							{#if ms.gaps.today_bucket}<span class="ctx-sc">{ms.gaps.today_bucket} bucket</span>{/if}
							{#if ms.gaps.today_fill_probability != null}
								<span class="ctx-sc mono">{pct(ms.gaps.today_fill_probability)} fill</span>
							{/if}
						</div>
					{/if}
					<table class="gap-table">
						<thead>
							<tr>
								<th>Size bucket</th>
								<th class="num">n</th>
								<th class="bar-col">Fill rate</th>
							</tr>
						</thead>
						<tbody>
							{#each ms.gaps.buckets as b (b.bucket)}
								<tr>
									<td class="bk">{b.bucket}</td>
									<td class="num mono">{b.count}</td>
									<td class="bar-col">
										{#if b.fill_rate != null}
											<span class="g-bar">
												<span
													class="g-bar-fill"
													style:width="{b.fill_rate * 100}%"
													style:background={b.fill_rate >= 0.66
														? 'var(--up)'
														: b.fill_rate >= 0.45
															? 'var(--lvl-flip)'
															: 'var(--down)'}
												></span>
											</span>
											<span class="g-bar-val mono">{pct(b.fill_rate)}</span>
										{:else}
											<span class="muted">—</span>
										{/if}
									</td>
								</tr>
							{:else}
								<tr><td colspan="3" class="muted">No gap history available.</td></tr>
							{/each}
						</tbody>
					</table>
					<p class="note caption">
						The headline "~70% of gaps fill" is a <strong>small-gap artifact</strong>: tiny gaps
						fill ~90%+, but large (≥2%) gaps fill far less — often nearer ~30%. Always read the fill
						rate for the relevant size bucket, never one blended number.
					</p>
				{:else}
					<p class="muted">Gap statistics unavailable.</p>
				{/if}
			</div>
		</section>

		<!-- 4 · methodology footnotes -->
		<section class="panel block method" in:fly={enter(6)}>
			<div class="block-head">
				<h2>What this is — and isn't</h2>
			</div>
			<ul class="foot">
				<li>
					<strong>It describes a regime, it does not predict returns.</strong> The composite labels the
					current backdrop (risk-on/off, calm/stressed); it is a slow prior, not a same-day directional
					trigger.
				</li>
				<li>
					<strong>RORO is the signed direction</strong> — each signal is z-scored and oriented (+ =
					risk-off), then combined on a documented prior (not fit to returns).
				</li>
				<li>
					<strong>The γ-modifier is a conviction gate, not a direction.</strong> Dealer gamma scales
					how hard to act on the volatility-regime axis (pinned vs trending); it never flips or amplifies
					the signed bias.
				</li>
				<li>
					<strong>regime_score = sign(roro) × actionability</strong>, where actionability = |roro| ×
					γ-modifier — the sign is preserved, only the magnitude is scaled.
				</li>
				<li>
					<strong>Divergence is an instability warning.</strong> Alignment across components is the
					signal; a lone disagreeing component flags fragility, not a trade.
				</li>
				<li>
					<strong>Context gates dispersion / tilt, not the read.</strong> Event risk widens expected
					range, seasonality is a small capped tilt, and gap fill rates are size-conditioned.
				</li>
			</ul>
		</section>
	{/if}
</main>

<style>
	/* — app bar (mirrors the dashboard) — */
	.appbar {
		position: sticky;
		top: 0;
		z-index: 50;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.7rem max(1.25rem, calc((100% - 1100px) / 2));
		background: color-mix(in oklab, var(--bg-0) 78%, transparent);
		backdrop-filter: blur(14px) saturate(140%);
		border-bottom: 1px solid var(--border);
		transition: var(--theme-tx);
	}
	.brand {
		display: inline-flex;
		align-items: center;
		gap: 0.55rem;
		text-decoration: none;
		color: var(--text-hi);
	}
	.brand .mark {
		display: grid;
		place-items: center;
		width: 28px;
		height: 28px;
		border-radius: 8px;
		font-weight: 800;
		font-size: 1.05rem;
		color: var(--bg-0);
		background: linear-gradient(145deg, var(--gold), #b8862b);
		box-shadow: 0 2px 10px -2px rgba(227, 179, 65, 0.5);
	}
	.brand .word {
		font-weight: 600;
		letter-spacing: 0.12em;
		font-size: 0.82rem;
		color: var(--text-mid);
	}
	.brand .word b {
		color: var(--text-hi);
		font-weight: 800;
	}
	.seg {
		position: relative;
		display: grid;
		grid-auto-flow: column;
		grid-auto-columns: 1fr;
		gap: 2px;
		padding: 3px;
		background: var(--surface-1);
		border: 1px solid var(--border);
		border-radius: var(--r-pill);
		transition: var(--theme-tx);
	}
	.seg-ind {
		position: absolute;
		top: 3px;
		bottom: 3px;
		left: 3px;
		width: calc((100% - 6px) / var(--n));
		transform: translateX(calc(var(--i) * 100%));
		background: var(--accent);
		border-radius: var(--r-pill);
		box-shadow: 0 2px 12px -2px var(--accent);
		transition: transform var(--dur-2) var(--ease-out);
	}
	.seg button {
		position: relative;
		z-index: 1;
		background: none;
		border: none;
		color: var(--text-mid);
		font: inherit;
		font-weight: 700;
		font-size: 0.8rem;
		letter-spacing: 0.03em;
		padding: 0.35rem 0.95rem;
		cursor: pointer;
		transition: color var(--dur-1);
	}
	.seg button.active {
		color: #fff;
	}
	.seg button:not(.active):hover {
		color: var(--text-hi);
	}
	.status {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		font-size: 0.78rem;
	}
	.live {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		color: var(--text-lo);
		font-weight: 700;
		letter-spacing: 0.08em;
		font-size: 0.68rem;
	}
	.live i {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: var(--text-lo);
	}
	.live.on {
		color: var(--up);
	}
	.live.on i {
		background: var(--up);
		box-shadow: 0 0 0 0 rgba(46, 211, 144, 0.6);
		animation: pulse 2.4s ease-out infinite;
	}
	@keyframes pulse {
		0% {
			box-shadow: 0 0 0 0 rgba(46, 211, 144, 0.55);
		}
		70% {
			box-shadow: 0 0 0 7px rgba(46, 211, 144, 0);
		}
		100% {
			box-shadow: 0 0 0 0 rgba(46, 211, 144, 0);
		}
	}
	.updated {
		color: var(--text-lo);
	}
	.icon-btn {
		display: grid;
		place-items: center;
		width: 30px;
		height: 30px;
		padding: 0;
		color: var(--text-mid);
		background: none;
		border: 1px solid var(--border);
		border-radius: var(--r-pill);
		cursor: pointer;
		transition:
			color var(--dur-1),
			border-color var(--dur-1),
			background var(--dur-1);
	}
	.icon-btn svg {
		width: 16px;
		height: 16px;
		fill: none;
		stroke: currentColor;
		stroke-width: 2;
		stroke-linecap: round;
	}
	.icon-btn:hover {
		color: var(--text-hi);
		border-color: var(--border-strong);
		background: var(--surface-2);
	}
	.conn {
		color: var(--text-mid);
		text-decoration: none;
		font-weight: 600;
		padding: 0.3rem 0.7rem;
		border: 1px solid var(--border);
		border-radius: var(--r-pill);
		white-space: nowrap;
		transition:
			border-color var(--dur-1),
			color var(--dur-1),
			background var(--dur-1);
	}
	.conn:hover {
		color: var(--text-hi);
		border-color: var(--border-strong);
		background: var(--surface-2);
	}

	/* — page shell — */
	main {
		max-width: 1100px;
		margin: 0 auto;
		padding: 1.5rem 1.25rem 4rem;
	}
	.page-head h1 {
		margin: 0;
		font-size: 1.5rem;
		letter-spacing: -0.01em;
		color: var(--text-hi);
	}
	.lede {
		margin: 0.45rem 0 1.3rem;
		max-width: 70ch;
		color: var(--text-mid);
		font-size: 0.9rem;
		line-height: 1.5;
	}

	/* — hero gauge — */
	.hero {
		padding: 1.4rem 1.5rem;
		margin-bottom: 1rem;
	}
	.hero-main {
		display: flex;
		align-items: center;
		gap: 2rem;
		flex-wrap: wrap;
	}
	.hero-meta {
		display: flex;
		flex-direction: column;
		min-width: 11rem;
	}
	.bias {
		font-size: 1rem;
		font-weight: 800;
		letter-spacing: 0.05em;
	}
	.score {
		font-size: 3rem;
		font-weight: 800;
		line-height: 1;
	}
	.score-cap {
		margin-top: 0.35rem;
		font-size: 0.68rem;
		color: var(--text-lo);
	}
	.gauge {
		position: relative;
		flex: 1;
		min-width: 260px;
		height: 30px;
	}
	.track {
		position: absolute;
		top: 12px;
		left: 0;
		right: 0;
		height: 6px;
		border-radius: var(--r-pill);
		background: linear-gradient(90deg, var(--up), var(--surface-3) 50%, var(--down));
	}
	.needle {
		position: absolute;
		top: 3px;
		width: 4px;
		height: 24px;
		border-radius: 2px;
		background: var(--text-hi);
		box-shadow: 0 0 6px var(--text-faint);
		transform: translateX(-50%);
		transition: left var(--dur-3) var(--ease-out);
	}
	.g-lab {
		position: absolute;
		top: 22px;
		font-size: 0.62rem;
		color: var(--text-faint);
	}
	.g-lab.on {
		left: 0;
	}
	.g-lab.mid {
		left: 50%;
		transform: translateX(-50%);
	}
	.g-lab.off {
		right: 0;
	}
	.hero-stats {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 0.8rem;
		margin-top: 1.4rem;
		padding-top: 1.2rem;
		border-top: 1px solid var(--border);
	}
	.stat {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}
	.stat .k {
		font-size: 0.66rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--text-lo);
		font-weight: 700;
	}
	.stat .v {
		font-size: 1.3rem;
		font-weight: 800;
		line-height: 1.1;
		color: var(--text-hi);
	}
	.stat .v.na {
		color: var(--text-lo);
	}
	.stat .sub-k {
		font-size: 0.66rem;
		color: var(--text-faint);
	}
	.flags {
		display: flex;
		flex-wrap: wrap;
		gap: 0.45rem;
		margin-top: 1.2rem;
	}
	.flag {
		font-size: 0.7rem;
		font-weight: 600;
		color: var(--text-lo);
		background: var(--surface-2);
		border: 1px solid var(--border);
		border-radius: var(--r-pill);
		padding: 0.16rem 0.6rem;
	}
	.flag.warn {
		color: var(--lvl-flip);
		border-color: color-mix(in oklab, var(--lvl-flip) 40%, transparent);
	}

	/* — generic block — */
	.block {
		padding: 1.2rem 1.4rem;
		margin-bottom: 1rem;
	}
	.block-head {
		display: flex;
		align-items: baseline;
		gap: 0.6rem;
		flex-wrap: wrap;
		margin-bottom: 1rem;
	}
	.block-head h2 {
		margin: 0;
		font-size: 0.74rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--text-lo);
		font-weight: 700;
	}
	.block-sub {
		font-size: 0.72rem;
		color: var(--text-faint);
	}

	/* — signal breakdown — */
	.signals {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
	.s-top {
		display: flex;
		align-items: baseline;
		gap: 0.6rem;
	}
	.s-label {
		font-weight: 700;
		color: var(--text-hi);
		text-transform: capitalize;
		font-size: 0.86rem;
	}
	.s-bias {
		font-size: 0.66rem;
		font-weight: 700;
		letter-spacing: 0.04em;
	}
	.s-score {
		margin-left: auto;
		font-size: 0.86rem;
		font-weight: 800;
	}
	.bar {
		position: relative;
		display: block;
		height: 10px;
		margin: 0.4rem 0;
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
	.s-detail {
		display: block;
		color: var(--text-mid);
		font-size: 0.76rem;
		line-height: 1.4;
	}
	.unavail {
		margin: 1rem 0 0;
		font-size: 0.7rem;
		color: var(--text-faint);
	}

	/* — learned overlay (§7) — */
	.learned-grid {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 0.9rem;
		margin: 0.4rem 0 0.2rem;
	}

	/* — context grid — */
	.ctx-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 1rem;
		margin-bottom: 1rem;
	}
	.gaps {
		grid-column: 1 / -1;
	}
	.ctx-lead {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.55rem;
		margin-bottom: 0.8rem;
	}
	.ctx-pill {
		font-size: 0.74rem;
		font-weight: 800;
		letter-spacing: 0.04em;
		color: var(--text-hi);
		background: var(--surface-2);
		border: 1px solid var(--border);
		border-radius: var(--r-pill);
		padding: 0.18rem 0.6rem;
	}
	.ctx-lead.hot .ctx-pill {
		color: var(--lvl-flip);
		border-color: color-mix(in oklab, var(--lvl-flip) 40%, transparent);
	}
	.ctx-sc {
		font-size: 0.72rem;
		color: var(--text-lo);
	}
	.chips {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
	}
	.chips li {
		font-size: 0.74rem;
		color: var(--text-mid);
		background: var(--surface-2);
		border: 1px solid var(--border);
		border-radius: var(--r-pill);
		padding: 0.14rem 0.55rem;
	}
	.chips li.muted {
		background: none;
		border: none;
		padding-left: 0;
	}
	.muted {
		color: var(--text-faint);
		font-size: 0.76rem;
	}
	.note {
		margin: 0.85rem 0 0;
		font-size: 0.72rem;
		line-height: 1.5;
		color: var(--text-lo);
	}
	.note.caption {
		color: var(--text-mid);
	}
	.note strong {
		color: var(--text-hi);
	}

	/* — gap table — */
	.gap-table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.8rem;
	}
	.gap-table th {
		text-align: left;
		font-size: 0.64rem;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--text-lo);
		font-weight: 700;
		padding: 0 0.6rem 0.5rem 0;
		border-bottom: 1px solid var(--border);
	}
	.gap-table td {
		padding: 0.5rem 0.6rem 0.5rem 0;
		border-bottom: 1px solid var(--border);
		vertical-align: middle;
	}
	.gap-table .bk {
		font-weight: 600;
		color: var(--text-hi);
	}
	.gap-table .num {
		text-align: right;
		width: 3rem;
		color: var(--text-mid);
	}
	.gap-table .bar-col {
		width: 55%;
		display: flex;
		align-items: center;
		gap: 0.6rem;
	}
	.g-bar {
		position: relative;
		flex: 1;
		height: 8px;
		background: var(--surface-2);
		border-radius: var(--r-pill);
		overflow: hidden;
	}
	.g-bar-fill {
		position: absolute;
		left: 0;
		top: 0;
		bottom: 0;
		border-radius: var(--r-pill);
		transition: width var(--dur-3) var(--ease-out);
	}
	.g-bar-val {
		min-width: 2.6rem;
		text-align: right;
		color: var(--text-hi);
		font-weight: 700;
	}

	/* — methodology footnotes — */
	.method .foot {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 0.7rem;
	}
	.method .foot li {
		font-size: 0.8rem;
		line-height: 1.5;
		color: var(--text-mid);
		padding-left: 0.9rem;
		border-left: 2px solid var(--border-strong);
	}
	.method .foot strong {
		color: var(--text-hi);
	}

	/* — skeleton + error — */
	.skeletons {
		display: grid;
		gap: 1rem;
	}
	.sk {
		border-radius: var(--r-md);
		background:
			linear-gradient(100deg, transparent 20%, rgba(255, 255, 255, 0.05) 40%, transparent 60%),
			var(--surface-1);
		background-size:
			200% 100%,
			auto;
		border: 1px solid var(--border);
		animation: shimmer 1.4s linear infinite;
	}
	.sk-hero {
		height: 200px;
	}
	.sk-wide {
		height: 240px;
	}
	@keyframes shimmer {
		to {
			background-position:
				-200% 0,
				0 0;
		}
	}
	.error {
		background: var(--down-dim);
		border: 1px solid color-mix(in oklab, var(--down) 45%, transparent);
		border-radius: var(--r-md);
		padding: 1rem 1.25rem;
		color: var(--text-hi);
	}
	.hint {
		margin-top: 0.5rem;
		color: var(--text-mid);
		font-size: 0.85rem;
	}
	.hint code {
		font-family: var(--font-mono);
		background: var(--surface-2);
		padding: 0.1rem 0.4rem;
		border-radius: 6px;
	}

	@media (max-width: 760px) {
		.hero-stats {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
		.learned-grid {
			grid-template-columns: 1fr;
		}
		.ctx-grid {
			grid-template-columns: 1fr;
		}
		.appbar {
			flex-wrap: wrap;
		}
	}
</style>
