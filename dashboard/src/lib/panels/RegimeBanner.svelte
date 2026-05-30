<script lang="ts">
	import { formatGex } from '$lib/api';
	import AnimatedNumber from '$lib/AnimatedNumber.svelte';
	import type { GammaLevels } from '$lib/types';

	let { levels }: { levels: GammaLevels } = $props();

	const positive = $derived(levels.regime === 'positive');
	const blurb = $derived(
		positive
			? 'Dealers long gamma — hedging dampens moves (sell rallies, buy dips). Mean-reverting tape.'
			: 'Dealers short gamma — hedging amplifies moves (buy rallies, sell dips). Trending, unstable tape.'
	);
</script>

<div class="banner" class:pos={positive} class:neg={!positive}>
	<div class="glow" aria-hidden="true"></div>
	<div class="left">
		<div class="tag">
			<span class="ind"></span>
			{positive ? 'POSITIVE GAMMA' : 'NEGATIVE GAMMA'}
		</div>
		<div class="blurb">{blurb}</div>
	</div>
	<div class="right">
		<AnimatedNumber class="net" value={levels.net_gex} format={formatGex} />
		<div class="net-label">Net GEX / 1% move</div>
	</div>
</div>

<style>
	.banner {
		position: relative;
		overflow: hidden;
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
		border-radius: var(--r-md);
		padding: 1.05rem 1.3rem;
		border: 1px solid var(--border);
		background: linear-gradient(180deg, var(--surface-1), var(--bg-1));
		transition: var(--theme-tx);
	}
	.pos {
		border-color: color-mix(in oklab, var(--up) 38%, transparent);
	}
	.neg {
		border-color: color-mix(in oklab, var(--down) 38%, transparent);
	}
	.glow {
		position: absolute;
		inset: 0;
		pointer-events: none;
	}
	.pos .glow {
		background: radial-gradient(420px 120px at 0% 50%, var(--up-dim), transparent 70%);
	}
	.neg .glow {
		background: radial-gradient(420px 120px at 0% 50%, var(--down-dim), transparent 70%);
	}
	.left,
	.right {
		position: relative;
		z-index: 1;
	}
	.tag {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		font-weight: 800;
		letter-spacing: 0.08em;
		font-size: 0.9rem;
	}
	.ind {
		width: 9px;
		height: 9px;
		border-radius: 50%;
	}
	.pos .tag {
		color: var(--up);
	}
	.pos .ind {
		background: var(--up);
		box-shadow: 0 0 12px var(--up);
	}
	.neg .tag {
		color: var(--down);
	}
	.neg .ind {
		background: var(--down);
		box-shadow: 0 0 12px var(--down);
	}
	.blurb {
		color: var(--text-mid);
		font-size: 0.85rem;
		margin-top: 0.35rem;
		max-width: 52ch;
		line-height: 1.4;
	}
	.right {
		text-align: right;
	}
	:global(.net) {
		font-size: 1.7rem;
		font-weight: 700;
		letter-spacing: -0.01em;
		color: var(--text-hi);
	}
	.net-label {
		font-size: 0.68rem;
		color: var(--text-lo);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		margin-top: 0.15rem;
	}
</style>
