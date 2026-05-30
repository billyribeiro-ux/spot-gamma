<script lang="ts">
	import { fetchThinkScript } from '$lib/api';
	import type { GammaLevels, Symbol } from '$lib/types';

	// Re-fetch when symbol changes (or levels refresh). The engine renders the
	// study so the dashboard copy is byte-identical to the CLI output — one
	// source of truth.
	let { symbol, levels }: { symbol: Symbol; levels: GammaLevels } = $props();

	let script = $state('');
	let error = $state(false);

	$effect(() => {
		const sym = symbol;
		void levels; // refresh when the snapshot updates
		let alive = true;
		fetchThinkScript(sym)
			.then((s) => alive && ((script = s), (error = false)))
			.catch(() => alive && (error = true));
		return () => {
			alive = false;
		};
	});

	let copied = $state(false);
	async function copy() {
		await navigator.clipboard.writeText(script);
		copied = true;
		setTimeout(() => (copied = false), 1500);
	}
</script>

<div class="panel card">
	<div class="head">
		<div class="title">
			<h2>ThinkScript Export</h2>
			<span class="sub">levels · flip zone · regime background · alerts</span>
		</div>
		<button class:done={copied} disabled={!script} onclick={copy}>{copied ? '✓ Copied' : 'Copy'}</button>
	</div>
	{#if error}
		<p class="err">Couldn't render the study.</p>
	{:else}
		<pre class="mono">{script}</pre>
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
		margin-bottom: 0.7rem;
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
	button {
		background: var(--accent);
		color: #fff;
		border: 1px solid transparent;
		border-radius: var(--r-sm);
		padding: 0.35rem 0.9rem;
		font-weight: 700;
		font-size: 0.78rem;
		cursor: pointer;
		transition:
			background var(--dur-1),
			transform var(--dur-1);
	}
	button:hover:not(:disabled) {
		background: color-mix(in oklab, var(--accent) 85%, white);
	}
	button:active:not(:disabled) {
		transform: scale(0.96);
	}
	button:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}
	button.done {
		background: var(--up-dim);
		color: var(--up);
		border-color: color-mix(in oklab, var(--up) 40%, transparent);
	}
	.err {
		color: var(--down);
		font-size: 0.85rem;
		margin: 0;
	}
	pre {
		margin: 0;
		background: var(--bg-0);
		border: 1px solid var(--border);
		border-radius: var(--r-sm);
		padding: 0.8rem 0.9rem;
		max-height: 320px;
		overflow: auto;
		font-size: 0.74rem;
		color: var(--text-mid);
		line-height: 1.55;
	}
</style>
