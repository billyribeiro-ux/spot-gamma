<script lang="ts">
	import type { GammaLevels } from '$lib/types';
	import { formatGex } from '$lib/api';

	let { levels }: { levels: GammaLevels } = $props();

	const positive = $derived(levels.regime === 'positive');
	const blurb = $derived(
		positive
			? 'Dealers long gamma — hedging dampens moves (sell rallies, buy dips). Mean-reverting tape.'
			: 'Dealers short gamma — hedging amplifies moves (buy rallies, sell dips). Trending / unstable tape.'
	);
</script>

<div class="banner" class:pos={positive} class:neg={!positive}>
	<div class="left">
		<div class="tag">{positive ? 'POSITIVE GAMMA' : 'NEGATIVE GAMMA'}</div>
		<div class="blurb">{blurb}</div>
	</div>
	<div class="right">
		<div class="net">{formatGex(levels.net_gex)}</div>
		<div class="net-label">Net GEX / 1%</div>
	</div>
</div>

<style>
	.banner {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
		border-radius: 12px;
		padding: 1rem 1.25rem;
		border: 1px solid;
	}
	.pos {
		background: rgba(34, 197, 94, 0.08);
		border-color: rgba(34, 197, 94, 0.4);
	}
	.neg {
		background: rgba(239, 68, 68, 0.08);
		border-color: rgba(239, 68, 68, 0.4);
	}
	.tag {
		font-weight: 700;
		letter-spacing: 0.06em;
		font-size: 0.9rem;
	}
	.pos .tag {
		color: #4ade80;
	}
	.neg .tag {
		color: #f87171;
	}
	.blurb {
		color: #9ca3af;
		font-size: 0.85rem;
		margin-top: 0.25rem;
		max-width: 48ch;
	}
	.net {
		font-size: 1.6rem;
		font-weight: 700;
		font-variant-numeric: tabular-nums;
		text-align: right;
		color: #f3f4f6;
	}
	.net-label {
		font-size: 0.7rem;
		color: #6b7280;
		text-align: right;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
</style>
