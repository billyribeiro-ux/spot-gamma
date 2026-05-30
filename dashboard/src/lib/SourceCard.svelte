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
		background: linear-gradient(180deg, var(--surface-1), var(--bg-1));
		border: 1px solid var(--border);
		border-radius: var(--r-md);
		padding: 1rem 1.2rem;
		box-shadow: var(--shadow-1);
		transition:
			border-color var(--dur-1),
			box-shadow var(--dur-2),
			transform var(--dur-2);
	}
	.card:hover {
		border-color: var(--border-strong);
		transform: translateY(-1px);
	}
	.card.active {
		border-color: color-mix(in oklab, var(--accent) 55%, transparent);
		box-shadow: 0 0 0 1px var(--accent-dim), var(--shadow-2);
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
		background: var(--text-faint);
	}
	.dot.on {
		background: var(--up);
		box-shadow: 0 0 8px var(--up);
	}
	.label {
		font-weight: 700;
	}
	.kind {
		font-size: 0.6rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		padding: 0.1rem 0.45rem;
		border-radius: var(--r-pill);
		color: var(--bg-0);
		font-weight: 800;
	}
	.badge-active {
		font-size: 0.6rem;
		font-weight: 800;
		color: var(--accent);
		letter-spacing: 0.1em;
	}
	.notes {
		color: var(--text-mid);
		font-size: 0.82rem;
		line-height: 1.45;
		margin: 0.5rem 0 0.85rem;
	}
	.nokey {
		color: var(--text-lo);
		font-size: 0.82rem;
		margin: 0 0 0.85rem;
	}
	.fields {
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
		margin-bottom: 0.85rem;
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
	}
	.fl {
		font-size: 0.74rem;
		color: var(--text-mid);
	}
	.fl em {
		color: var(--text-lo);
		font-style: normal;
	}
	.saved {
		color: var(--up);
		margin-left: 0.4rem;
		font-size: 0.66rem;
		font-weight: 700;
	}
	.saved.env {
		color: var(--gold);
	}
	input {
		background: var(--bg-0);
		border: 1px solid var(--border);
		border-radius: var(--r-sm);
		padding: 0.5rem 0.65rem;
		color: var(--text-hi);
		font-size: 0.85rem;
		font-family: var(--font-mono);
		transition: border-color var(--dur-1);
	}
	input::placeholder {
		color: var(--text-faint);
	}
	input:focus {
		outline: none;
		border-color: var(--accent);
		box-shadow: 0 0 0 3px var(--accent-dim);
	}
	.actions {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}
	button {
		border: 1px solid var(--border-strong);
		background: var(--surface-2);
		color: var(--text-hi);
		border-radius: var(--r-sm);
		padding: 0.42rem 0.95rem;
		font-size: 0.8rem;
		font-weight: 700;
		cursor: pointer;
		transition:
			border-color var(--dur-1),
			background var(--dur-1),
			transform var(--dur-1);
	}
	button:hover:not(:disabled) {
		background: var(--surface-3);
		border-color: var(--text-lo);
	}
	button:active:not(:disabled) {
		transform: scale(0.97);
	}
	button:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}
	button.test {
		background: var(--accent);
		border-color: var(--accent);
		color: #fff;
	}
	button.test:hover:not(:disabled) {
		background: color-mix(in oklab, var(--accent) 85%, white);
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
		padding: 0.55rem 0.75rem;
		border-radius: var(--r-sm);
	}
	.result.ok {
		background: var(--up-dim);
		color: var(--up);
		border: 1px solid color-mix(in oklab, var(--up) 35%, transparent);
	}
	.result.fail {
		background: var(--down-dim);
		color: var(--down);
		border: 1px solid color-mix(in oklab, var(--down) 35%, transparent);
	}
	.rdot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: currentColor;
		flex: none;
		box-shadow: 0 0 8px currentColor;
	}
	.rmsg {
		flex: 1;
		word-break: break-word;
	}
	.lat {
		color: var(--text-lo);
		font-variant-numeric: tabular-nums;
	}
</style>
