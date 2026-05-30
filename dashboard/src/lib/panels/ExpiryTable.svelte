<script lang="ts">
	import type { GammaLevels } from '$lib/types';
	import { formatGex } from '$lib/api';

	let { levels }: { levels: GammaLevels } = $props();
</script>

<div class="card">
	<h2>Gamma by Expiration</h2>
	<table>
		<thead>
			<tr><th>Expiry</th><th>DTE</th><th>Net GEX</th></tr>
		</thead>
		<tbody>
			{#each levels.by_expiry as e (e.expiration)}
				<tr>
					<td>{e.expiration}{e.dte_days === 0 ? ' (0DTE)' : ''}</td>
					<td class="num">{e.dte_days}</td>
					<td class="num" class:pos={e.net_gex >= 0} class:neg={e.net_gex < 0}>{formatGex(e.net_gex)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	.card {
		background: #111827;
		border: 1px solid #1f2937;
		border-radius: 12px;
		padding: 1rem 1.25rem;
	}
	h2 {
		margin: 0 0 0.75rem;
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: #9ca3af;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.85rem;
	}
	th {
		text-align: left;
		color: #6b7280;
		font-weight: 500;
		padding-bottom: 0.4rem;
		border-bottom: 1px solid #1f2937;
	}
	td {
		padding: 0.4rem 0;
		border-bottom: 1px solid #1f2937;
		color: #d1d5db;
	}
	.num {
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	.pos {
		color: #4ade80;
	}
	.neg {
		color: #f87171;
	}
</style>
