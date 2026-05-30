<script lang="ts">
	import { browser } from '$app/environment';
	import { Canvas } from '@threlte/core';
	import GammaScene from './GammaScene.svelte';
	import type { GammaLevels } from '$lib/types';

	let { levels }: { levels: GammaLevels } = $props();

	// Respect the user's reduced-motion preference: no idle auto-rotation.
	const autoRotate =
		!browser || !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
</script>

<section class="panel">
	<header>
		<h2>Gamma terrain</h2>
		<span class="hint">net GEX by strike · drag to orbit, scroll to zoom</span>
	</header>
	<div class="canvas-wrap">
		<!-- WebGL is client-only; the static prerender ships just the shell. -->
		{#if browser}
			<Canvas>
				<GammaScene {levels} {autoRotate} />
			</Canvas>
		{/if}
	</div>
</section>

<style>
	.panel {
		padding: 0.95rem 1.1rem;
	}
	header {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		margin-bottom: 0.6rem;
	}
	h2 {
		margin: 0;
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--text-lo);
		font-weight: 700;
	}
	.hint {
		font-size: 0.72rem;
		color: var(--text-lo);
	}
	.canvas-wrap {
		width: 100%;
		height: 340px;
		border-radius: var(--r-sm);
		overflow: hidden;
		background: radial-gradient(circle at 50% 25%, #0d1424 0%, var(--bg-0) 72%);
	}
</style>
