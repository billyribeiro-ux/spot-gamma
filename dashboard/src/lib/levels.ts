// Pure helpers for the SpotGamma level overlays — extracted from PriceChart so
// the dedupe / range / domain logic is unit-testable without a browser.
import type { GammaLevels } from './types';

export type LevelKey =
	| 'spot'
	| 'call_wall'
	| 'put_wall'
	| 'gamma_flip'
	| 'vol_trigger'
	| 'abs_gamma'
	| 'hedge_wall';

export interface LevelDef {
	key: LevelKey;
	label: string;
	color: string;
	pick: (l: GammaLevels) => number | null;
}

// Priority order — when two levels coincide, the earlier one wins.
export const LEVELS: LevelDef[] = [
	{ key: 'spot', label: 'Spot', color: '#f3f6fc', pick: (l) => l.spot },
	{ key: 'call_wall', label: 'Call Wall', color: '#2ed390', pick: (l) => l.call_wall },
	{ key: 'put_wall', label: 'Put Wall', color: '#ff5269', pick: (l) => l.put_wall },
	{ key: 'gamma_flip', label: 'Gamma Flip', color: '#f5b14c', pick: (l) => l.zero_gamma },
	{ key: 'vol_trigger', label: 'Vol Trigger', color: '#b487ff', pick: (l) => l.volatility_trigger },
	{ key: 'abs_gamma', label: 'Abs Gamma', color: '#36c7e0', pick: (l) => l.absolute_gamma },
	{ key: 'hedge_wall', label: 'Hedge Wall', color: '#ff9d4d', pick: (l) => l.hedge_wall }
];

export type Visibility = Record<LevelKey, boolean>;

export const allVisible = (): Visibility =>
	Object.fromEntries(LEVELS.map((d) => [d.key, true])) as Visibility;

/** Prices of the levels that are present and toggled on. */
export function visibleLevelPrices(levels: GammaLevels, visible: Visibility): number[] {
	return LEVELS.filter((d) => visible[d.key])
		.map((d) => d.pick(levels))
		.filter((v): v is number => v != null);
}

/** Min/max of the visible level prices (drives the chart's autoscale union). */
export function levelRange(levels: GammaLevels, visible: Visibility): { min: number; max: number } | null {
	const ps = visibleLevelPrices(levels, visible);
	return ps.length ? { min: Math.min(...ps), max: Math.max(...ps) } : null;
}

/** Shared price domain = candle range ∪ level range, padded. */
export function priceDomain(
	candle: { lo: number; hi: number } | null,
	range: { min: number; max: number } | null,
	pad = 0.02
): [number, number] | null {
	const los = [candle?.lo, range?.min].filter((v): v is number => v != null);
	const his = [candle?.hi, range?.max].filter((v): v is number => v != null);
	if (!los.length || !his.length) return null;
	const lo = Math.min(...los);
	const hi = Math.max(...his);
	const p = (hi - lo) * pad || 1;
	return [lo - p, hi + p];
}

export interface LevelLine {
	key: LevelKey;
	label: string;
	color: string;
	price: number;
}

/** The visible level lines to draw, with coincident prices deduped by priority. */
export function visibleLevelLines(levels: GammaLevels, visible: Visibility): LevelLine[] {
	const seen = new Set<number>();
	const out: LevelLine[] = [];
	for (const d of LEVELS) {
		if (!visible[d.key]) continue;
		const price = d.pick(levels);
		if (price == null) continue;
		const rounded = Math.round(price * 100) / 100;
		if (seen.has(rounded)) continue;
		seen.add(rounded);
		out.push({ key: d.key, label: d.label, color: d.color, price });
	}
	return out;
}
