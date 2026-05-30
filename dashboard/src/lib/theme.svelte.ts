// Theme: 'dark' (default) | 'light'. Persists to localStorage and reflects on
// <html data-theme>, which app.css uses to swap token values. SSR-safe.
import { browser } from '$app/environment';

export type Theme = 'dark' | 'light';
const KEY = 'spotgamma-theme';

function initial(): Theme {
	if (!browser) return 'dark';
	const saved = localStorage.getItem(KEY);
	if (saved === 'light' || saved === 'dark') return saved;
	// default to dark (the terminal aesthetic); only honor an explicit light pref
	return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

class ThemeState {
	current = $state<Theme>('dark');

	constructor() {
		if (browser) {
			this.current = initial();
			this.apply();
		}
	}

	private apply() {
		document.documentElement.dataset.theme = this.current;
	}

	toggle() {
		this.current = this.current === 'dark' ? 'light' : 'dark';
		if (browser) {
			localStorage.setItem(KEY, this.current);
			this.apply();
		}
	}
}

export const theme = new ThemeState();
