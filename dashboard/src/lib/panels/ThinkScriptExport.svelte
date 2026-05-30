<script lang="ts">
	import type { GammaLevels } from '$lib/types';

	let { levels }: { levels: GammaLevels } = $props();

	function fmt(v: number | null): string {
		return v === null ? '0' : v.toFixed(2);
	}

	// Mirror engine/spotgamma/export_thinkscript.py so the dashboard's copy
	// matches the CLI-generated study.
	const script = $derived(
		`# Spot Gamma Levels - ${levels.symbol} (regime: ${levels.regime})\n` +
			`input zeroGamma = ${fmt(levels.zero_gamma)};\n` +
			`input callWall = ${fmt(levels.call_wall)};\n` +
			`input putWall = ${fmt(levels.put_wall)};\n` +
			`input volTrigger = ${fmt(levels.volatility_trigger)};\n\n` +
			`plot ZeroGammaLine = zeroGamma;\n` +
			`plot CallWallLine = callWall;\n` +
			`plot PutWallLine = putWall;\n` +
			`plot VolTriggerLine = volTrigger;`
	);

	let copied = $state(false);
	async function copy() {
		await navigator.clipboard.writeText(script);
		copied = true;
		setTimeout(() => (copied = false), 1500);
	}
</script>

<div class="card">
	<div class="head">
		<h2>ThinkScript Export</h2>
		<button onclick={copy}>{copied ? 'Copied!' : 'Copy'}</button>
	</div>
	<pre>{script}</pre>
</div>

<style>
	.card {
		background: #111827;
		border: 1px solid #1f2937;
		border-radius: 12px;
		padding: 1rem 1.25rem;
	}
	.head {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}
	h2 {
		margin: 0;
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: #9ca3af;
	}
	button {
		background: #2563eb;
		color: #fff;
		border: none;
		border-radius: 6px;
		padding: 0.3rem 0.8rem;
		font-size: 0.8rem;
		cursor: pointer;
	}
	button:hover {
		background: #1d4ed8;
	}
	pre {
		margin: 0;
		background: #0b0f17;
		border-radius: 8px;
		padding: 0.75rem;
		font-size: 0.75rem;
		color: #cbd5e1;
		overflow-x: auto;
		font-family: ui-monospace, monospace;
	}
</style>
