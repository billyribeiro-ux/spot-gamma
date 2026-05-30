<script lang="ts">
	import { formatGex } from '$lib/api';
	import type { GammaLevels } from '$lib/types';

	let { levels }: { levels: GammaLevels } = $props();
	const maxAbs = $derived(Math.max(1, ...levels.by_expiry.map((e) => Math.abs(e.net_gex))));
</script>

<div class="panel card">
	<h2>Gamma by Expiration</h2>
	<div class="scroll">
		<table>
			<thead>
				<tr><th>Expiry</th><th class="num">DTE</th><th class="num">Net GEX</th></tr>
			</thead>
			<tbody>
				{#each levels.by_expiry as e (e.expiration)}
					{@const w = (Math.abs(e.net_gex) / maxAbs) * 100}
					<tr class:zero-dte={e.dte_days === 0}>
						<td>
							{e.expiration}
							{#if e.dte_days === 0}<span class="badge">0DTE</span>{/if}
						</td>
						<td class="num dte">{e.dte_days}</td>
						<td class="num">
							<span class="cell">
								<span class="bar" class:pos={e.net_gex >= 0} class:neg={e.net_gex < 0} style:width="{w}%"
								></span>
								<span class="val" class:pos={e.net_gex >= 0} class:neg={e.net_gex < 0}>{formatGex(e.net_gex)}</span>
							</span>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>

<style>
	.card {
		padding: 1rem 1.2rem;
	}
	h2 {
		margin: 0 0 0.6rem;
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--text-lo);
		font-weight: 700;
	}
	.scroll {
		max-height: 340px;
		overflow-y: auto;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.85rem;
	}
	thead th {
		position: sticky;
		top: 0;
		background: var(--surface-1);
		text-align: left;
		color: var(--text-lo);
		font-weight: 600;
		font-size: 0.7rem;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		padding: 0 0 0.45rem;
		border-bottom: 1px solid var(--border);
	}
	td {
		padding: 0.4rem 0;
		border-bottom: 1px solid var(--border);
		color: var(--text-mid);
	}
	tbody tr {
		transition: background var(--dur-1);
	}
	tbody tr:hover {
		background: var(--surface-2);
	}
	.num {
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	.dte {
		color: var(--text-lo);
		width: 3rem;
	}
	.zero-dte td:first-child {
		box-shadow: inset 2px 0 0 var(--accent);
	}
	.badge {
		margin-left: 0.4rem;
		font-size: 0.6rem;
		font-weight: 700;
		letter-spacing: 0.05em;
		color: var(--accent);
		background: var(--accent-dim);
		padding: 0.05rem 0.35rem;
		border-radius: 4px;
		vertical-align: middle;
	}
	.cell {
		position: relative;
		display: inline-flex;
		justify-content: flex-end;
		min-width: 7.5rem;
	}
	.bar {
		position: absolute;
		right: 0;
		top: 50%;
		transform: translateY(-50%);
		height: 60%;
		border-radius: 3px;
		opacity: 0.18;
		transition: width var(--dur-3) var(--ease-out);
	}
	.bar.pos {
		background: var(--up);
	}
	.bar.neg {
		background: var(--down);
	}
	.val {
		position: relative;
		font-weight: 600;
	}
	.val.pos {
		color: var(--up);
	}
	.val.neg {
		color: var(--down);
	}
</style>
