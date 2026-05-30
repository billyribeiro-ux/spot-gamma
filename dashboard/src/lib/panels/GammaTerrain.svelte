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
		background: #111827;
		border: 1px solid #1f2937;
		border-radius: 12px;
		padding: 0.9rem 1rem;
	}
	header {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		margin-bottom: 0.5rem;
	}
	h2 {
		margin: 0;
		font-size: 0.95rem;
	}
	.hint {
		font-size: 0.72rem;
		color: #6b7280;
	}
	.canvas-wrap {
		width: 100%;
		height: 340px;
		border-radius: 8px;
		overflow: hidden;
		background: radial-gradient(circle at 50% 30%, #0f1626 0%, #0b0f17 70%);
	}
</style>
