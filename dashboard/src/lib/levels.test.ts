import { describe, expect, it } from 'vitest';
import { allVisible, levelRange, priceDomain, visibleLevelLines } from './levels';
import type { GammaLevels } from './types';

// Minimal levels object: hedge_wall coincides with call_wall (7600); abs_gamma
// is the far-low level (7000); put_wall is null (absent).
const LEVELS_FIXTURE = {
	spot: 7580,
	call_wall: 7600,
	put_wall: null,
	zero_gamma: 7352.56,
	volatility_trigger: 7355,
	absolute_gamma: 7000,
	hedge_wall: 7600
} as unknown as GammaLevels;

describe('visibleLevelLines', () => {
	it('dedupes coincident prices in priority order (Call Wall beats Hedge Wall)', () => {
		const lines = visibleLevelLines(LEVELS_FIXTURE, allVisible());
		const at7600 = lines.filter((l) => l.price === 7600);
		expect(at7600).toHaveLength(1);
		expect(at7600[0].key).toBe('call_wall'); // earlier in priority order wins
	});

	it('skips null and hidden levels', () => {
		const v = allVisible();
		v.abs_gamma = false;
		const keys = visibleLevelLines(LEVELS_FIXTURE, v).map((l) => l.key);
		expect(keys).not.toContain('put_wall'); // null
		expect(keys).not.toContain('abs_gamma'); // toggled off
		expect(keys).toContain('gamma_flip');
	});
});

describe('levelRange', () => {
	it('spans only the visible, present levels', () => {
		expect(levelRange(LEVELS_FIXTURE, allVisible())).toEqual({ min: 7000, max: 7600 });
	});

	it('shrinks when a far level is hidden', () => {
		const v = allVisible();
		v.abs_gamma = false; // drop the 7000 floor
		expect(levelRange(LEVELS_FIXTURE, v)).toEqual({ min: 7352.56, max: 7600 });
	});

	it('is null when nothing is visible', () => {
		const v = allVisible();
		for (const k of Object.keys(v) as (keyof typeof v)[]) v[k] = false;
		expect(levelRange(LEVELS_FIXTURE, v)).toBeNull();
	});
});

describe('priceDomain', () => {
	it('unions candle range with level range and pads', () => {
		const d = priceDomain({ lo: 7470, hi: 7625 }, { min: 7000, max: 7600 });
		expect(d).not.toBeNull();
		// min from levels (7000), max from candles (7625), padded outward
		expect(d![0]).toBeLessThan(7000);
		expect(d![1]).toBeGreaterThan(7625);
	});

	it('returns null without any bounds', () => {
		expect(priceDomain(null, null)).toBeNull();
	});
});
