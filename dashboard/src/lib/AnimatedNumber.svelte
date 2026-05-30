<script lang="ts">
	import { untrack } from 'svelte';
	import { Tween } from 'svelte/motion';
	import { DUR, easeOut, motionOK } from './motion';

	// Smoothly interpolates to its target when the value changes (e.g. on each
	// data refresh). First paint is instant — no gimmicky count-from-zero — and
	// it collapses to instant under reduced-motion. With `flash`, it also pulses
	// green/red for one beat in the direction the value moved (a trading tick).
	let {
		value,
		format = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 2 }),
		duration = DUR.slow,
		flash = false,
		class: klass = ''
	}: {
		value: number;
		format?: (n: number) => string;
		duration?: number;
		flash?: boolean;
		class?: string;
	} = $props();

	// Initial value/duration are read once at construction (intentional); the
	// $effect drives subsequent transitions when `value` changes.
	const tween = new Tween(untrack(() => value), {
		duration: untrack(() => (motionOK() ? duration : 0)),
		easing: easeOut
	});

	let prev = untrack(() => value);
	let flashClass = $state('');
	let flashSeq = 0;

	$effect(() => {
		tween.target = value;
		if (flash && motionOK() && value !== prev) {
			const dir = value > prev ? 'flash-up' : 'flash-down';
			const seq = ++flashSeq;
			// retrigger cleanly even on rapid successive ticks
			flashClass = '';
			requestAnimationFrame(() => {
				if (seq === flashSeq) flashClass = dir;
			});
		}
		prev = value;
	});
</script>

<span class="tnum {klass} {flashClass}">{format(tween.current)}</span>
