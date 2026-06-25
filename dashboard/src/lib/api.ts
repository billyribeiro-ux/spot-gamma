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

export interface MSSignal {
	key: string;
	label: string;
	value: number;
	score: number;
	bias: 'risk-on' | 'neutral' | 'risk-off';
	detail: string;
}

export interface MSEventRisk {
	events: string[];
	score: number;
	label: 'quiet' | 'elevated' | 'high';
}
export interface MSSeasonality {
	factors: string[];
	tilt: number;
	label: 'bullish tilt' | 'bearish tilt' | 'neutral';
}
export interface MSGaps {
	today_gap_pct: number | null;
	today_bucket: string | null;
	today_fill_probability: number | null;
	buckets: { bucket: string; count: number; fill_rate: number | null }[];
}

/** Empirical forward-return bucket the current composite score falls into. */
export interface MSLearnedCalibration {
	n: number;
	mean_fwd: number;
	pct_positive: number;
}

/**
 * §7 learned overlay — present only when a validated model artifact exists
 * (`spotgamma learn`). The regime read is unchanged unless a learned variant
 * beat the documented prior out-of-sample; this surfaces the measured, OOS
 * relationships, never a forecast.
 */
export interface MSLearned {
	horizon: number;
	trained_through: string | null;
	adopt_weights: boolean;
	adopt_tilt: boolean;
	oos_ic: number;
	tilt_fwd_return: number | null; // null unless the tilt was adopted OOS
	calibration: MSLearnedCalibration | null;
}

export interface MarketStructure {
	symbol: string;
	regime_score: number;
	roro_score: number;
	actionability: number;
	gamma_modifier: number;
	gamma_available: boolean;
	bias: 'risk-on' | 'neutral' | 'risk-off';
	vol_regime: 'calm' | 'normal' | 'stressed' | 'crisis';
	divergence: boolean;
	flip_transition_risk: boolean;
	signals: MSSignal[];
	event_risk: MSEventRisk | null;
	seasonality: MSSeasonality | null;
	gaps: MSGaps | null;
	learned: MSLearned | null;
	inputs: Record<string, number | null>;
	unavailable: string[];
}

/** Composite market-structure regime read (vol + macro + dealer gamma). */
export async function fetchMarketStructure(symbol: Symbol): Promise<MarketStructure> {
	const res = await fetch(`${BASE}/market-structure?symbol=${symbol}`);
	if (!res.ok) throw new Error(`API ${res.status} for ${symbol} market-structure`);
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
