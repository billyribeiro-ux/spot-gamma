import type { GammaLevels, History, Symbol, Timeframe } from './types';

// On the web, vite proxies /api -> FastAPI (see vite.config.ts). The bundled
// desktop app has no proxy, so it sets VITE_API_BASE to the backend URL.
export const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';
const BASE = API_BASE;

export async function fetchLevels(symbol: Symbol): Promise<GammaLevels> {
	const res = await fetch(`${BASE}/levels/${symbol}`);
	if (!res.ok) {
		const detail = await res.json().catch(() => ({}));
		throw new Error(detail.detail ?? `API ${res.status} for ${symbol}`);
	}
	return res.json();
}

export async function fetchHistory(symbol: Symbol, tf: Timeframe): Promise<History> {
	const res = await fetch(`${BASE}/history/${symbol}?tf=${tf}`);
	if (!res.ok) {
		const detail = await res.json().catch(() => ({}));
		throw new Error(detail.detail ?? `API ${res.status} for ${symbol} ${tf}`);
	}
	return res.json();
}

/** Engine-rendered ThinkScript study (single source of truth with the CLI). */
export async function fetchThinkScript(symbol: Symbol): Promise<string> {
	const res = await fetch(`${BASE}/thinkscript/${symbol}`);
	if (!res.ok) throw new Error(`API ${res.status} for ${symbol} thinkscript`);
	return res.text();
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
