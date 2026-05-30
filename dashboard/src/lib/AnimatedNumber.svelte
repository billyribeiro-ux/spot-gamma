<script lang="ts">
	import { untrack } from 'svelte';
	import { Tween } from 'svelte/motion';
	import { DUR, easeOut, motionOK } from './motion';

	// Smoothly interpolates to its target when the value changes (e.g. on each
	// data refresh). First paint is instant — no gimmicky count-from-zero — and
	// it collapses to instant under reduced-motion.
	let {
		value,
		format = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 2 }),
		duration = DUR.slow,
		class: klass = ''
	}: {
		value: number;
		format?: (n: number) => string;
		duration?: number;
		class?: string;
	} = $props();

	// Initial value/duration are read once at construction (intentional); the
	// $effect drives subsequent transitions when `value` changes.
	const tween = new Tween(untrack(() => value), {
		duration: untrack(() => (motionOK() ? duration : 0)),
		easing: easeOut
	});
	$effect(() => {
		tween.target = value;
	});
</script>

<span class="tnum {klass}">{format(tween.current)}</span>
