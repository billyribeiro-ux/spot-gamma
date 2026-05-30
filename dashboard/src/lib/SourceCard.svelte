<script lang="ts">
	import { saveCredentials, testConnection, setActive, type SourceStatus, type TestResult } from '$lib/admin';

	let { source, onchange }: { source: SourceStatus; onchange: () => void } = $props();

	// Local editable buffer for field values. Seeded from the prop and topped up
	// when the source refreshes (e.g. a non-secret value saved server-side),
	// without clobbering anything the user is mid-typing.
	let values = $state<Record<string, string>>({});
	$effect(() => {
		for (const f of source.fields) {
			if (!(f.key in values)) values[f.key] = f.value;
		}
	});
	let busy = $state(false);
	let result = $state<TestResult | null>(null);

	const kindColor: Record<string, string> = {
		free: '#22c55e',
		broker: '#3b82f6',
		vendor: '#a855f7',
		local: '#eab308',
		offline: '#6b7280'
	};

	async function onSave() {
		busy = true;
		result = null;
		try {
			await saveCredentials(source.name, values);
			// clear typed secrets from the box; backend now holds them
			for (const f of source.fields) if (f.secret) values[f.key] = '';
			onchange();
		} finally {
			busy = false;
		}
	}

	async function onTest() {
		busy = true;
		try {
			result = await testConnection(source.name, values);
		} catch (e) {
			result = { name: source.name, ok: false, message: String(e), latency_ms: 0 };
		} finally {
			busy = false;
		}
	}

	async function onActivate() {
		busy = true;
		try {
			await setActive(source.name);
			onchange();
		} finally {
			busy = false;
		}
	}
</script>

<div class="card" class:active={source.active}>
	<div class="head">
		<div class="title">
			<span class="dot" class:on={source.configured}></span>
			<span class="label">{source.label}</span>
			<span class="kind" style:background={kindColor[source.kind] ?? '#6b7280'}>{source.kind}</span>
		</div>
		{#if source.active}
			<span class="badge-active">ACTIVE</span>
		{/if}
	</div>

	<p class="notes">{source.notes}</p>

	{#if source.needs_credentials}
		<div class="fields">
			{#each source.fields as f (f.key)}
				<label>
					<span class="fl">
						{f.label}{#if !f.required}<em> (optional)</em>{/if}
						{#if f.saved}<span class="saved">saved</span>{:else if f.env_fallback}<span class="saved env">from env</span>{/if}
					</span>
					<input
						type={f.secret ? 'password' : 'text'}
						bind:value={values[f.key]}
						placeholder={f.saved ? '•••••••• (saved — leave blank to keep)' : f.placeholder || f.env}
						autocomplete="off"
						spellcheck="false"
					/>
				</label>
			{/each}
		</div>
	{:else}
		<p class="nokey">No credentials needed.</p>
	{/if}

	<div class="actions">
		{#if source.needs_credentials}
			<button onclick={onSave} disabled={busy}>Save</button>
		{/if}
		<button class="test" onclick={onTest} disabled={busy}>{busy ? 'Testing…' : 'Test connection'}</button>
		<button class="activate" onclick={onActivate} disabled={busy || source.active || !source.configured}>
			{source.active ? 'Active' : 'Set active'}
		</button>
	</div>

	{#if result}
		<div class="result" class:ok={result.ok} class:fail={!result.ok}>
			<span class="rdot"></span>
			<span class="rmsg">{result.ok ? 'Connected' : 'Failed'} — {result.message}</span>
			{#if result.latency_ms}<span class="lat">{result.latency_ms}ms</span>{/if}
		</div>
	{/if}
</div>

<style>
	.card {
		background: #111827;
		border: 1px solid #1f2937;
		border-radius: 12px;
		padding: 1rem 1.25rem;
	}
	.card.active {
		border-color: #2563eb;
	}
	.head {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	.title {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.dot {
		width: 9px;
		height: 9px;
		border-radius: 50%;
		background: #4b5563;
	}
	.dot.on {
		background: #22c55e;
	}
	.label {
		font-weight: 600;
	}
	.kind {
		font-size: 0.62rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		padding: 0.1rem 0.4rem;
		border-radius: 4px;
		color: #0b0f17;
		font-weight: 700;
	}
	.badge-active {
		font-size: 0.62rem;
		font-weight: 700;
		color: #93c5fd;
		letter-spacing: 0.08em;
	}
	.notes {
		color: #9ca3af;
		font-size: 0.82rem;
		margin: 0.5rem 0 0.75rem;
	}
	.nokey {
		color: #6b7280;
		font-size: 0.82rem;
		margin: 0 0 0.75rem;
	}
	.fields {
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
		margin-bottom: 0.75rem;
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}
	.fl {
		font-size: 0.75rem;
		color: #9ca3af;
	}
	.fl em {
		color: #6b7280;
		font-style: normal;
	}
	.saved {
		color: #4ade80;
		margin-left: 0.4rem;
		font-size: 0.68rem;
	}
	.saved.env {
		color: #fbbf24;
	}
	input {
		background: #0b0f17;
		border: 1px solid #374151;
		border-radius: 6px;
		padding: 0.45rem 0.6rem;
		color: #e5e7eb;
		font-size: 0.85rem;
		font-family: ui-monospace, monospace;
	}
	input:focus {
		outline: none;
		border-color: #2563eb;
	}
	.actions {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}
	button {
		border: 1px solid #374151;
		background: #1f2937;
		color: #e5e7eb;
		border-radius: 6px;
		padding: 0.4rem 0.9rem;
		font-size: 0.82rem;
		font-weight: 600;
		cursor: pointer;
	}
	button:hover:not(:disabled) {
		border-color: #4b5563;
	}
	button:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}
	button.test {
		background: #2563eb;
		border-color: #2563eb;
		color: #fff;
	}
	button.activate {
		background: transparent;
	}
	.result {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-top: 0.75rem;
		font-size: 0.82rem;
		padding: 0.5rem 0.7rem;
		border-radius: 6px;
	}
	.result.ok {
		background: rgba(34, 197, 94, 0.1);
		color: #86efac;
	}
	.result.fail {
		background: rgba(239, 68, 68, 0.1);
		color: #fca5a5;
	}
	.rdot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: currentColor;
		flex: none;
	}
	.rmsg {
		flex: 1;
		word-break: break-word;
	}
	.lat {
		color: #6b7280;
		font-variant-numeric: tabular-nums;
	}
</style>
