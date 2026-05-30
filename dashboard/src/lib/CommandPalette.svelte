<script lang="ts">
	import { tick } from 'svelte';
	import { SvelteMap } from 'svelte/reactivity';
	import { fly, fade } from 'svelte/transition';
	import { easeOut, motionOK } from './motion';

	export interface Command {
		id: string;
		label: string;
		group: string;
		hint?: string; // e.g. current value / shortcut
		keywords?: string;
		run: () => void;
	}

	let { commands, open = $bindable(false) }: { commands: Command[]; open?: boolean } = $props();

	let query = $state('');
	let active = $state(0);
	let input = $state<HTMLInputElement | null>(null);

	const D = motionOK() ? 1 : 0;

	const filtered = $derived.by(() => {
		const q = query.trim().toLowerCase();
		if (!q) return commands;
		return commands.filter((c) => `${c.label} ${c.group} ${c.keywords ?? ''}`.toLowerCase().includes(q));
	});

	// group the filtered list while preserving order
	const groups = $derived.by(() => {
		const m = new SvelteMap<string, Command[]>();
		for (const c of filtered) (m.get(c.group) ?? m.set(c.group, []).get(c.group)!).push(c);
		return [...m.entries()];
	});

	// flat index -> command, for keyboard navigation across groups
	const flat = $derived(filtered);

	$effect(() => {
		// keep the active index in range as the list shrinks
		if (active >= flat.length) active = Math.max(0, flat.length - 1);
	});

	function hide() {
		open = false;
	}

	// focus + reset the field whenever the palette becomes visible (works whether
	// it's opened via ⌘K or by the parent setting `open`).
	$effect(() => {
		if (open) {
			query = '';
			active = 0;
			tick().then(() => input?.focus());
		}
	});

	function choose(c: Command) {
		c.run();
		hide();
	}

	function onWindowKey(e: KeyboardEvent) {
		if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
			e.preventDefault();
			open = !open;
			return;
		}
		if (!open) return;
		if (e.key === 'Escape') {
			e.preventDefault();
			hide();
		} else if (e.key === 'ArrowDown') {
			e.preventDefault();
			active = Math.min(active + 1, flat.length - 1);
		} else if (e.key === 'ArrowUp') {
			e.preventDefault();
			active = Math.max(active - 1, 0);
		} else if (e.key === 'Enter') {
			e.preventDefault();
			const c = flat[active];
			if (c) choose(c);
		}
	}
</script>

<svelte:window onkeydown={onWindowKey} />

{#if open}
	<!-- backdrop button: click or Esc (window handler) to dismiss -->
	<button
		class="scrim"
		type="button"
		aria-label="Close command palette"
		transition:fade={{ duration: 140 * D }}
		onclick={hide}
	></button>
	<div class="wrap">
		<div
			class="palette panel"
			role="dialog"
			aria-modal="true"
			aria-label="Command palette"
			transition:fly={{ y: -12, duration: 220 * D, easing: easeOut }}
		>
			<div class="search">
				<svg viewBox="0 0 24 24" class="mag" aria-hidden="true">
					<circle cx="11" cy="11" r="7" />
					<line x1="16.5" y1="16.5" x2="21" y2="21" />
				</svg>
				<input
					bind:this={input}
					bind:value={query}
					type="text"
					placeholder="Search symbols, timeframes, actions…"
					spellcheck="false"
					autocomplete="off"
				/>
				<kbd>ESC</kbd>
			</div>

			<div class="results" role="listbox" tabindex="-1">
				{#if flat.length === 0}
					<div class="empty">No matching commands</div>
				{:else}
					{#each groups as [group, items] (group)}
						<div class="group-label">{group}</div>
						{#each items as c (c.id)}
							{@const idx = flat.indexOf(c)}
							<button
								class="row"
								class:active={idx === active}
								role="option"
								aria-selected={idx === active}
								onmouseenter={() => (active = idx)}
								onclick={() => choose(c)}
							>
								<span class="row-label">{c.label}</span>
								{#if c.hint}<span class="row-hint">{c.hint}</span>{/if}
							</button>
						{/each}
					{/each}
				{/if}
			</div>

			<div class="foot">
				<span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
				<span><kbd>↵</kbd> select</span>
				<span class="grow"></span>
				<span class="brand">Spot Gamma</span>
			</div>
		</div>
	</div>
{/if}

<style>
	.scrim {
		position: fixed;
		inset: 0;
		z-index: 100;
		background: rgba(4, 6, 11, 0.55);
		backdrop-filter: blur(3px);
	}
	.wrap {
		position: fixed;
		inset: 0;
		z-index: 101;
		display: flex;
		align-items: flex-start;
		justify-content: center;
		padding: 14vh 1rem 1rem;
		pointer-events: none; /* let clicks outside the dialog fall through to .scrim */
	}
	.scrim {
		border: none;
		cursor: default;
		padding: 0;
	}
	.palette {
		pointer-events: auto;
	}
	.palette {
		width: min(620px, 100%);
		max-height: 60vh;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		box-shadow: var(--shadow-2);
		border-color: var(--border-strong);
	}
	.search {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		padding: 0.85rem 1rem;
		border-bottom: 1px solid var(--border);
	}
	.mag {
		width: 18px;
		height: 18px;
		flex: none;
		fill: none;
		stroke: var(--text-lo);
		stroke-width: 2;
		stroke-linecap: round;
	}
	input {
		flex: 1;
		background: none;
		border: none;
		color: var(--text-hi);
		font: inherit;
		font-size: 0.98rem;
		outline: none;
	}
	input::placeholder {
		color: var(--text-faint);
	}
	.results {
		overflow-y: auto;
		padding: 0.4rem;
	}
	.group-label {
		font-size: 0.64rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--text-lo);
		font-weight: 700;
		padding: 0.6rem 0.7rem 0.3rem;
	}
	.row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		width: 100%;
		text-align: left;
		background: none;
		border: none;
		border-radius: var(--r-sm);
		padding: 0.55rem 0.7rem;
		color: var(--text-mid);
		font: inherit;
		font-size: 0.9rem;
		cursor: pointer;
	}
	.row.active {
		background: var(--accent-dim);
		color: var(--text-hi);
		box-shadow: inset 2px 0 0 var(--accent);
	}
	.row-hint {
		font-size: 0.74rem;
		color: var(--text-lo);
		font-variant-numeric: tabular-nums;
	}
	.empty {
		padding: 1.4rem;
		text-align: center;
		color: var(--text-lo);
		font-size: 0.88rem;
	}
	.foot {
		display: flex;
		align-items: center;
		gap: 0.9rem;
		padding: 0.55rem 0.9rem;
		border-top: 1px solid var(--border);
		font-size: 0.7rem;
		color: var(--text-lo);
	}
	.grow {
		flex: 1;
	}
	.brand {
		font-weight: 700;
		letter-spacing: 0.06em;
		color: var(--text-mid);
	}
	kbd {
		font-family: var(--font-mono);
		font-size: 0.66rem;
		background: var(--surface-2);
		border: 1px solid var(--border);
		border-radius: 4px;
		padding: 0.05rem 0.35rem;
		margin: 0 0.1rem;
		color: var(--text-mid);
	}
</style>
