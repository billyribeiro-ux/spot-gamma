import { render } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import GexProfile from './GexProfile.svelte';
import { allVisible } from '$lib/levels';
import type { GammaLevels } from '$lib/types';

function fixture(): GammaLevels {
	return {
		symbol: 'SPX',
		spot: 7580,
		timestamp: '2026-05-30T00:00:00Z',
		net_gex: 9e10,
		regime: 'positive',
		zero_gamma: 7352,
		volatility_trigger: 7355,
		call_wall: 7600,
		put_wall: 7100,
		absolute_gamma: 7000,
		hedge_wall: 7600,
		top_positive_nodes: [],
		top_negative_nodes: [],
		by_strike: [
			{ strike: 7000, call_gex: 1e8, put_gex: -2e8 },
			{ strike: 7300, call_gex: 3e8, put_gex: -1e8 },
			{ strike: 7600, call_gex: 5e8, put_gex: -1e8 },
			{ strike: 9000, call_gex: 1e8, put_gex: 0 } // outside the domain below
		],
		by_expiry: [],
		zero_dte_net_gex: 0,
		zero_dte_share: 0
	};
}

describe('GexProfile', () => {
	it('draws one bar per strike within the price domain', () => {
		const { container } = render(GexProfile, {
			props: { levels: fixture(), domain: [6900, 7700] as [number, number], height: 360 }
		});
		// 3 of 4 strikes fall inside [6900, 7700]; the 9000 strike is excluded
		expect(container.querySelectorAll('rect')).toHaveLength(3);
	});

	it('honors level visibility for the guide ticks', () => {
		const v = allVisible();
		const all = render(GexProfile, {
			props: { levels: fixture(), domain: [6900, 7700] as [number, number], visible: v }
		});
		const shown = all.container.querySelectorAll('line').length;

		v.call_wall = false;
		v.put_wall = false;
		v.abs_gamma = false;
		const fewer = render(GexProfile, {
			props: { levels: fixture(), domain: [6900, 7700] as [number, number], visible: v }
		});
		expect(fewer.container.querySelectorAll('line').length).toBeLessThan(shown);
	});
});
