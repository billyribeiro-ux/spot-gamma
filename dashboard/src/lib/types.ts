// Mirrors spotgamma.models.GammaLevels (the API response shape).

export interface StrikeGamma {
	strike: number;
	call_gex: number;
	put_gex: number;
}

export interface ExpiryGamma {
	expiration: string;
	net_gex: number;
	dte_days: number;
}

export interface GammaLevels {
	symbol: string;
	spot: number;
	timestamp: string;
	net_gex: number;
	regime: 'positive' | 'negative';
	zero_gamma: number | null;
	volatility_trigger: number | null;
	call_wall: number | null;
	put_wall: number | null;
	top_positive_nodes: StrikeGamma[];
	top_negative_nodes: StrikeGamma[];
	by_strike: StrikeGamma[];
	by_expiry: ExpiryGamma[];
	zero_dte_net_gex: number;
	zero_dte_share: number;
}

export const SYMBOLS = ['SPX', 'NDX', 'SPY', 'QQQ'] as const;
export type Symbol = (typeof SYMBOLS)[number];
