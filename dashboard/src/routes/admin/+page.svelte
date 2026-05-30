<script lang="ts">
	import { getSources, type AdminSources } from '$lib/admin';
	import SourceCard from '$lib/SourceCard.svelte';

	let data = $state<AdminSources | null>(null);
	let error = $state<string | null>(null);

	async function load() {
		error = null;
		try {
			data = await getSources();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	$effect(() => {
		load();
	});
</script>

<svelte:head><title>Spot Gamma — Connections</title></svelte:head>

<main>
	<header>
		<div>
			<h1>Connections</h1>
			<p class="meta">
				Add a provider's API credentials, test the connection, and set the active data
				source for the dashboard. Secrets are stored locally and never displayed back.
			</p>
		</div>
		<a class="back" href="/">← Dashboard</a>
	</header>

	{#if error}
		<div class="error">
			<strong>Couldn't reach the API.</strong> {error}
			<div class="hint">Start it: <code>uvicorn api.main:app --port 8000</code></div>
		</div>
	{:else if !data}
		<div class="placeholder">Loading…</div>
	{:else}
		<div class="active-line">
			Active source: <strong>{data.active}</strong>
		</div>
		<div class="grid">
			{#each data.sources as s (s.name)}
				<SourceCard source={s} onchange={load} />
			{/each}
		</div>
		<p class="foot">
			Tip: <strong>cboe</strong> needs no credentials — set it active to run real (15-min
			delayed) data immediately.
		</p>
	{/if}
</main>

<style>
	:global(body) {
		margin: 0;
		background: #0b0f17;
		color: #e5e7eb;
		font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
	}
	main {
		max-width: 920px;
		margin: 0 auto;
		padding: 1.5rem 1.25rem 3rem;
	}
	header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1rem;
		margin-bottom: 1.25rem;
	}
	h1 {
		margin: 0;
		font-size: 1.4rem;
	}
	.meta {
		margin: 0.25rem 0 0;
		color: #6b7280;
		font-size: 0.82rem;
		max-width: 60ch;
	}
	.back {
		color: #93c5fd;
		text-decoration: none;
		font-size: 0.85rem;
		white-space: nowrap;
	}
	.active-line {
		color: #9ca3af;
		font-size: 0.9rem;
		margin-bottom: 1rem;
	}
	.active-line strong {
		color: #f3f4f6;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 1rem;
	}
	.foot {
		color: #6b7280;
		font-size: 0.82rem;
		margin-top: 1.25rem;
	}
	.error {
		background: rgba(239, 68, 68, 0.1);
		border: 1px solid rgba(239, 68, 68, 0.4);
		border-radius: 12px;
		padding: 1rem 1.25rem;
		color: #fca5a5;
	}
	.hint {
		margin-top: 0.5rem;
		color: #9ca3af;
		font-size: 0.85rem;
	}
	.placeholder {
		color: #6b7280;
		padding: 2rem 0;
	}
	@media (max-width: 720px) {
		.grid {
			grid-template-columns: 1fr;
		}
	}
</style>
