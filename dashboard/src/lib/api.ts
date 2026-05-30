import type { GammaLevels, Symbol } from './types';

// Vite proxies /api -> FastAPI backend (see vite.config.ts).
const BASE = '/api';

export async function fetchLevels(symbol: Symbol): Promise<GammaLevels> {
	const res = await fetch(`${BASE}/levels/${symbol}`);
	if (!res.ok) {
		const detail = await res.json().catch(() => ({}));
		throw new Error(detail.detail ?? `API ${res.status} for ${symbol}`);
	}
	return res.json();
}

/** Format a large dollar gamma number compactly, e.g. 3.78e8 -> "$378M". */
export function formatGex(value: number): string {
	const abs = Math.abs(value);
	const sign = value < 0 ? '-' : '';
	if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
	if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
	if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
	return `${sign}$${abs.toFixed(0)}`;
}

export function formatLevel(value: number | null): string {
	return value === null ? '—' : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
