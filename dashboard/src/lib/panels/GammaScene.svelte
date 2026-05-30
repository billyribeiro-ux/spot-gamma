<script lang="ts">
	import { T } from '@threlte/core';
	import { OrbitControls } from '@threlte/extras';
	import type { GammaLevels } from '$lib/types';

	let { levels, autoRotate = true }: { levels: GammaLevels; autoRotate?: boolean } = $props();

	const MAX_BARS = 48;
	const SPAN = 24; // world units across the strike axis
	const MAX_H = 6;

	// Net GEX per strike within a spot-centered window, normalized to bar heights.
	const model = $derived.by(() => {
		const lo = (levels.put_wall ?? levels.spot * 0.92) * 0.99;
		const hi = (levels.call_wall ?? levels.spot * 1.08) * 1.01;
		let r = levels.by_strike
			.filter((s) => s.strike >= lo && s.strike <= hi)
			.map((s) => ({ strike: s.strike, net: s.call_gex + s.put_gex }));
		if (r.length > MAX_BARS) {
			const keep = new Set(
				[...r].sort((a, b) => Math.abs(b.net) - Math.abs(a.net)).slice(0, MAX_BARS).map((x) => x.strike)
			);
			r = r.filter((x) => keep.has(x.strike));
		}
		r.sort((a, b) => a.strike - b.strike);
		const maxAbs = Math.max(1, ...r.map((d) => Math.abs(d.net)));
		const sLo = r[0]?.strike ?? lo;
		const sHi = r.at(-1)?.strike ?? hi;
		const span = sHi - sLo || 1;
		const bars = r.map((d) => ({
			strike: d.strike,
			net: d.net,
			x: ((d.strike - sLo) / span - 0.5) * SPAN,
			h: Math.max(0.05, (Math.abs(d.net) / maxAbs) * MAX_H)
		}));
		const barW = (SPAN / Math.max(bars.length, 1)) * 0.7;
		const spotX = ((levels.spot - sLo) / span - 0.5) * SPAN;
		return { bars, barW, spotX };
	});
</script>

<T.PerspectiveCamera makeDefault position={[0, 9, 21]} fov={48}>
	<OrbitControls enableDamping {autoRotate} autoRotateSpeed={0.5} enablePan={false} minDistance={10} maxDistance={46} maxPolarAngle={1.45} />
</T.PerspectiveCamera>

<T.AmbientLight intensity={0.55} />
<T.DirectionalLight position={[8, 16, 10]} intensity={1.4} />
<T.DirectionalLight position={[-10, 8, -6]} intensity={0.4} color="#93c5fd" />

<T.GridHelper args={[SPAN * 1.4, 28, '#243044', '#161c27']} />

{#each model.bars as b (b.strike)}
	<T.Mesh position={[b.x, b.h / 2, 0]}>
		<T.BoxGeometry args={[model.barW, b.h, 2]} />
		<T.MeshStandardMaterial
			color={b.net >= 0 ? '#2ed390' : '#ff5269'}
			emissive={b.net >= 0 ? '#0c6b4a' : '#7d1f2b'}
			emissiveIntensity={0.3}
			metalness={0.15}
			roughness={0.5}
		/>
	</T.Mesh>
{/each}

<!-- spot marker: a bright thin pillar at the current price -->
<T.Mesh position={[model.spotX, (MAX_H + 1.5) / 2, 0]}>
	<T.BoxGeometry args={[0.12, MAX_H + 1.5, 2.3]} />
	<T.MeshStandardMaterial color="#e5e7eb" emissive="#e5e7eb" emissiveIntensity={0.45} />
</T.Mesh>
