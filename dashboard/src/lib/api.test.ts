import { describe, expect, it } from 'vitest';
import { formatGex, formatLevel } from './api';

describe('formatGex', () => {
	it('formats billions/millions/thousands compactly', () => {
		expect(formatGex(9.378e10)).toBe('$93.78B');
		expect(formatGex(3.78e8)).toBe('$378.0M');
		expect(formatGex(4500)).toBe('$4.5K');
		expect(formatGex(250)).toBe('$250');
	});

	it('preserves sign', () => {
		expect(formatGex(-2.5e9)).toBe('-$2.50B');
		expect(formatGex(-1e6)).toBe('-$1.0M');
	});
});

describe('formatLevel', () => {
	it('renders a dash for null', () => {
		expect(formatLevel(null)).toBe('—');
	});
	it('formats numbers with grouping', () => {
		expect(formatLevel(7580.06)).toBe('7,580.06');
	});
});
