// Shared motion language. Durations/easings mirror app.css so JS- and
// CSS-driven motion feel like one system. All helpers degrade to instant when
// the user prefers reduced motion.
import { cubicOut, expoOut } from 'svelte/easing';

export const motionOK = (): boolean =>
	typeof window === 'undefined' || !window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export const DUR = { fast: 120, base: 220, slow: 420, slower: 640 } as const;

export const easeOut = expoOut;
export const easeStandard = cubicOut;

/** Stagger delay for list/panel entrances (capped so long lists stay snappy). */
export const stagger = (i: number, step = 55, max = 8): number => Math.min(i, max) * step;
